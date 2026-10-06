"""A Band on Discogs: its members, primary image and page (discogs_artist), and its genres and styles
(discogs_genres, asked separately because it costs a few more requests).

The artist is found through the Band's MusicBrainz "discogs" link (discogs.com/artist/<id>); without one, a Discogs
artist search counts only when exactly one result has exactly the Band's name (ignoring case and Discogs' "(2)"
disambiguation suffix), so a common name never matches the wrong artist.

Genres and styles aren't on the artist record: they're the most common styles, then genres, across up to three of
the artist's main masters, lower-cased.

Requests use Discogs' key/secret auth (settings.discogs_consumer_key/secret) and a descriptive User-Agent, paced to
at most one a second (the authenticated limit is 60 a minute). Missing credentials or any failure mean nothing;
this never raises.
"""
from __future__ import annotations

import logging
import re
import threading
import time as _time
from collections import Counter
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_API = "https://api.discogs.com"
_USER_AGENT = "the-list/0.1 +https://github.com/jsturgis/the_list"
_MASTERS = 3
MAX_GENRES = 5
_ARTIST_LINK = re.compile(r"discogs\.com/(?:[a-z]{2}/)?artist/(\d+)")
_SUFFIX = re.compile(r"\s*\(\d+\)$")  # "John Gallagher (2)" → "John Gallagher"

_pace_lock = threading.Lock()
_last_request = 0.0


@dataclass(frozen=True)
class DiscogsArtist:
    id: int
    name: str
    page_url: str
    members: list[dict] = field(default_factory=list)   # [{"name": ..., "active": bool}]
    image_url: str | None = None


def _plain_name(name: str) -> str:
    return _SUFFIX.sub("", name or "").strip()


def _get(client: httpx.Client, path: str, **params) -> dict:
    """A paced GET: at most one Discogs request a second."""
    global _last_request
    with _pace_lock:
        wait = 1.0 - (_time.monotonic() - _last_request)
        if wait > 0:
            _time.sleep(wait)
        try:
            return client.get(f"{_API}{path}", params=params or None).raise_for_status().json()
        finally:
            _last_request = _time.monotonic()


def _client(key: str, secret: str) -> httpx.Client:
    return httpx.Client(timeout=20, headers={"User-Agent": _USER_AGENT,
                                             "Authorization": f"Discogs key={key}, secret={secret}"})


def _credentials(key: str | None, secret: str | None) -> tuple[str, str] | None:
    key = key if key is not None else settings.discogs_consumer_key
    secret = secret if secret is not None else settings.discogs_consumer_secret
    return (key, secret) if key and secret else None


def _artist_id(client: httpx.Client, name: str, links: list[dict]) -> int | None:
    for link in links or []:
        if m := _ARTIST_LINK.search(link.get("url", "")):
            return int(m.group(1))
    # 100 a page, the most Discogs allows: a lone exact match has to be alone among them all, not just the first 50.
    results = _get(client, "/database/search", type="artist", q=name, per_page=100).get("results", [])
    exact = [r for r in results if _plain_name(r.get("title", "")).casefold() == name.strip().casefold()]
    return exact[0]["id"] if len(exact) == 1 else None


def discogs_artist(name: str, links: list[dict], client: httpx.Client | None = None,
                   key: str | None = None, secret: str | None = None) -> DiscogsArtist | None:
    """The Band's Discogs artist (members, primary image, page), or None (see the module docstring)."""
    creds = _credentials(key, secret)
    if creds is None:
        return None
    own_client = client is None
    if client is not None:
        client.headers.update({"User-Agent": _USER_AGENT, "Authorization": f"Discogs key={creds[0]}, secret={creds[1]}"})
    client = client or _client(*creds)
    try:
        artist_id = _artist_id(client, name, links)
        if artist_id is None:
            return None
        artist = _get(client, f"/artists/{artist_id}")
        images = artist.get("images") or []
        image = next((i for i in images if i.get("type") == "primary"), images[0] if images else None)
        return DiscogsArtist(
            id=artist["id"],
            name=_plain_name(artist.get("name", "")),
            page_url=artist.get("uri") or f"https://www.discogs.com/artist/{artist_id}",
            members=[{"name": _plain_name(m["name"]), "active": bool(m.get("active"))}
                     for m in artist.get("members") or [] if m.get("name")],
            image_url=(image or {}).get("uri") or None,
        )
    except Exception:
        logger.info("discogs: no artist for %s", name, exc_info=True)
        return None
    finally:
        if own_client:
            client.close()


def discogs_genres(artist_id: int, client: httpx.Client | None = None,
                   key: str | None = None, secret: str | None = None) -> list[str]:
    """The artist's most common styles, then genres, across up to three of its main masters; [] if none."""
    creds = _credentials(key, secret)
    if creds is None:
        return []
    own_client = client is None
    if client is not None:
        client.headers.update({"User-Agent": _USER_AGENT, "Authorization": f"Discogs key={creds[0]}, secret={creds[1]}"})
    client = client or _client(*creds)
    try:
        releases = _get(client, f"/artists/{artist_id}/releases", sort="year", sort_order="desc").get("releases", [])
        masters = [r["id"] for r in releases if r.get("type") == "master" and r.get("role") == "Main"][:_MASTERS]
        styles, genres = Counter(), Counter()
        for master_id in masters:
            master = _get(client, f"/masters/{master_id}")
            styles.update(s.lower() for s in master.get("styles") or [])
            genres.update(g.lower() for g in master.get("genres") or [])
        ranked = [s for s, _ in styles.most_common()] + [g for g, _ in genres.most_common()]
        return list(dict.fromkeys(ranked))[:MAX_GENRES]
    except Exception:
        logger.info("discogs: no genres for artist %s", artist_id, exc_info=True)
        return []
    finally:
        if own_client:
            client.close()
