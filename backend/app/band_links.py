"""A Band's links for the site, from MusicBrainz's artist-to-URL relationships (Band.links) and the edition's
own Spotify/SoundCloud/Bandcamp links (the fallback where MusicBrainz has none for that service).

Groups, in order:
  listening   up to 3 free services, then up to 3 paid ones, each ranked by service (below)
  follow      the Band's own profiles: Instagram, Facebook, X, TikTok, Bluesky, YouTube
  tour        tour dates: Bandsintown, Songkick
  about       Wikipedia, AllMusic, Discogs, Last.fm

A service is recognised by the link's host, not MusicBrainz's relationship type, which changes ("streaming
music" became "free streaming") and is inconsistent (Apple Music is "streaming" or "apple music").
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

MAX_FREE = 3
MAX_PAID = 3


@dataclass(frozen=True)
class Service:
    key: str
    label: str
    group: str        # listening | follow | tour | about
    paid: bool = False


# Ranked within each group: the first match of a group's services wins a place first. Each is (hosts, path
# prefix): a host matches itself and its subdomains (listen.tidal.com is Tidal). Order matters where hosts
# overlap: music.youtube.com is YouTube Music, not YouTube.
_AMAZON_MUSIC = tuple(f"music.amazon.{tld}" for tld in ("com", "co.uk", "de", "fr", "co.jp", "ca", "com.au", "es", "it"))
_SERVICES: list[tuple[tuple[str, ...], str, Service]] = [
    # Listening, free
    (("open.spotify.com",), "/artist/", Service("spotify", "Spotify", "listening")),
    (("music.youtube.com",), "", Service("youtube_music", "YouTube Music", "listening")),
    (("bandcamp.com",), "", Service("bandcamp", "Bandcamp", "listening")),
    (("soundcloud.com",), "", Service("soundcloud", "SoundCloud", "listening")),
    (("deezer.com",), "", Service("deezer", "Deezer", "listening")),
    (("audiomack.com",), "", Service("audiomack", "Audiomack", "listening")),
    # Listening, paid
    (("music.apple.com",), "", Service("apple_music", "Apple Music", "listening", paid=True)),
    (_AMAZON_MUSIC, "", Service("amazon_music", "Amazon Music", "listening", paid=True)),
    (("tidal.com",), "", Service("tidal", "Tidal", "listening", paid=True)),
    (("qobuz.com",), "", Service("qobuz", "Qobuz", "listening", paid=True)),
    # Follow
    (("instagram.com",), "", Service("instagram", "Instagram", "follow")),
    (("facebook.com",), "", Service("facebook", "Facebook", "follow")),
    (("twitter.com", "x.com"), "", Service("x", "X", "follow")),
    (("tiktok.com",), "", Service("tiktok", "TikTok", "follow")),
    (("bsky.app",), "", Service("bluesky", "Bluesky", "follow")),
    (("youtube.com",), "", Service("youtube", "YouTube", "follow")),
    # Tour dates
    (("bandsintown.com",), "", Service("bandsintown", "Bandsintown", "tour")),
    (("songkick.com",), "", Service("songkick", "Songkick", "tour")),
    # More about
    (("en.wikipedia.org",), "", Service("wikipedia", "Wikipedia", "about")),
    (("allmusic.com",), "", Service("allmusic", "AllMusic", "about")),
    (("discogs.com",), "", Service("discogs", "Discogs", "about")),
    (("last.fm",), "", Service("lastfm", "Last.fm", "about")),
]
_RANK = {service.key: i for i, (_, _, service) in enumerate(_SERVICES)}


@dataclass(frozen=True)
class BandLink:
    group: str
    service: str
    label: str
    url: str
    paid: bool = False


def service_for(url: str) -> Service | None:
    """The service a link belongs to, by host and path ("https://open.spotify.com/artist/…" is Spotify)."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().split(":")[0]
    if not host:
        return None
    for hosts, path, service in _SERVICES:
        if any(host == h or host.endswith("." + h) for h in hosts) and parsed.path.startswith(path):
            return service
    return None


def band_links(mb_links: list[dict] | None, *, spotify_url: str | None = None, soundcloud_url: str | None = None,
               bandcamp_url: str | None = None) -> list[BandLink]:
    """The Band's links for the site, grouped and ranked (see the module docstring). One link per service:
    MusicBrainz's first, else the edition's."""
    by_service: dict[str, BandLink] = {}
    edition = [u for u in (spotify_url, soundcloud_url, bandcamp_url) if u]
    for url in [link.get("url", "") for link in (mb_links or [])] + edition:
        service = service_for(url)
        if service and service.key not in by_service:
            by_service[service.key] = BandLink(service.group, service.key, service.label, url.strip(), service.paid)

    ranked = sorted(by_service.values(), key=lambda link: _RANK[link.service])
    free = [link for link in ranked if link.group == "listening" and not link.paid][:MAX_FREE]
    paid = [link for link in ranked if link.group == "listening" and link.paid][:MAX_PAID]
    rest = [link for link in ranked if link.group != "listening"]
    return free + paid + rest
