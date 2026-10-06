"""Tests for grouping and ranking a Band's links for the site."""
from __future__ import annotations

import pytest

from app.band_links import band_links, service_for


def _mb(*urls):
    return [{"type": "whatever", "url": u} for u in urls]


@pytest.mark.parametrize("url, service", [
    ("https://open.spotify.com/artist/6159IBm5gLPwG4BcJXseXc", "spotify"),
    ("https://open.spotify.com/playlist/37i9dQ", None),           # not an artist page
    ("https://soulfly.bandcamp.com/", "bandcamp"),
    ("https://music.youtube.com/channel/UC1", "youtube_music"),   # not YouTube
    ("https://www.youtube.com/user/soulfly", "youtube"),
    ("https://listen.tidal.com/artist/1", "tidal"),               # a subdomain
    ("https://music.amazon.co.uk/artists/B0", "amazon_music"),
    ("https://music.apple.com/us/artist/soulfly/1", "apple_music"),
    ("https://x.com/soulfly", "x"),
    ("https://twitter.com/soulfly", "x"),
    ("https://box.com/x.com/thing", None),                        # host, not a substring
    ("https://www.songkick.com/artists/1-soulfly", None),        # tour dates aren't shown
    ("https://www.bandsintown.com/a/1-soulfly", None),
    ("https://en.wikipedia.org/wiki/Soulfly", None),             # not shown: reference links aren't
    ("https://www.last.fm/music/Soulfly", None),
    ("not a url", None),
])
def test_service_for(url, service):
    found = service_for(url)
    assert (found.key if found else None) == service


def test_listening_is_three_free_then_three_paid_ranked_by_service():
    links = band_links(_mb(
        "https://www.deezer.com/artist/537",              # free, ranked 5th
        "https://music.apple.com/us/artist/1",            # paid, 1st
        "https://soundcloud.com/soulfly-15",               # free, 4th
        "https://open.qobuz.com/artist/1",                 # paid, 4th
        "https://open.spotify.com/artist/6159",            # free, 1st
        "https://tidal.com/browse/artist/1",               # paid, 3rd
        "https://soulfly.bandcamp.com/",                   # free, 3rd
        "https://music.amazon.com/artists/B0",             # paid, 2nd
    ))
    listening = [(link.service, link.paid) for link in links if link.group == "listening"]
    assert listening == [
        ("spotify", False), ("bandcamp", False), ("soundcloud", False),             # Deezer is 4th free: left out
        ("apple_music", True), ("amazon_music", True), ("tidal", True),            # Qobuz is 4th paid: left out
    ]


def test_other_groups_follow_listening_in_order():
    links = band_links(_mb(
        "https://www.allmusic.com/artist/mn1", "https://www.songkick.com/artists/1", "https://www.instagram.com/soulfly/",
        "https://en.wikipedia.org/wiki/Soulfly", "https://open.spotify.com/artist/1", "https://www.youtube.com/soulfly",
        "https://www.bandsintown.com/a/1",
    ))
    # Tour dates (Songkick, Bandsintown) and the reference links (AllMusic, Wikipedia) aren't shown.
    assert [(link.group, link.service) for link in links] == [
        ("listening", "spotify"),
        ("follow", "instagram"), ("follow", "youtube"),
    ]


def test_musicbrainz_wins_and_the_editions_links_fill_in():
    links = band_links(_mb("https://open.spotify.com/artist/mb"),
                       spotify_url="https://open.spotify.com/artist/edition",
                       bandcamp_url="https://soulfly.bandcamp.com/")
    assert [(link.service, link.url) for link in links] == [
        ("spotify", "https://open.spotify.com/artist/mb"),
        ("bandcamp", "https://soulfly.bandcamp.com/"),
    ]


def test_a_band_without_musicbrainz_links_keeps_the_editions():
    links = band_links([], soundcloud_url="https://soundcloud.com/x")
    assert [(link.group, link.label) for link in links] == [("listening", "SoundCloud")]


def test_unknown_links_and_duplicates_are_left_out():
    links = band_links(_mb("https://open.spotify.com/artist/1", "https://open.spotify.com/artist/2",
                           "https://viaf.org/viaf/1", "https://www.discogs.com/artist/1"))
    assert [(link.service, link.url) for link in links] == [("spotify", "https://open.spotify.com/artist/1")]
