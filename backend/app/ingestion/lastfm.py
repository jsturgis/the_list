"""A Band's genre tags from Last.fm: the top tags on its artist.getInfo, the genre source after MusicBrainz's
curated genres (the edition's genre is used only when every service has none).

Matched by the MusicBrainz id when there is one, so a namesake isn't picked up; otherwise (or when Last.fm doesn't
know that id) by the Band's exact name, with autocorrect off so "Gilman Youth" isn't corrected into someone else.
Tags are lower-cased and de-duplicated, at most five, without Last.fm's non-genre tags ("seen live", "favorites").
Needs settings.lastfm_api_key; without it, or on any failure, there are no tags. This never raises.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_API = "https://ws.audioscrobbler.com/2.0/"
_USER_AGENT = "the-list/0.1 (https://github.com/jsturgis/the_list)"
MAX_TAGS = 5
# Common Last.fm tags that say nothing about the kind of music: listening habits, places, voices and decades.
_NOT_GENRES = {
    "seen live", "favorite", "favorites", "favourite", "favourites", "albums i own", "love", "awesome", "beautiful",
    "under 2000 listeners", "spotify", "all",
    "american", "usa", "us", "british", "uk", "english", "canadian", "canada", "australian", "german", "swedish",
    "japanese", "french", "irish", "scottish", "mexican", "bay area", "san francisco", "oakland", "california",
    "los angeles", "new york", "seattle", "portland",
    "female vocalists", "male vocalists", "female vocalist", "male vocalist", "female vocals", "male vocals",
    "50s", "60s", "70s", "80s", "90s", "00s", "2000s", "2010s", "2020s",
}
_NOT_FOUND = 6


def _get_info(client: httpx.Client, api_key: str, **who: str) -> dict | None:
    """artist.getInfo for `who` (mbid=… or artist=…); None if Last.fm doesn't know the artist."""
    data = client.get(_API, params={"method": "artist.getinfo", "api_key": api_key, "format": "json", **who}
                      ).raise_for_status().json()
    if data.get("error") == _NOT_FOUND:
        return None
    if "error" in data:
        raise ValueError(f"Last.fm error {data['error']}: {data.get('message')}")
    return data["artist"]


def lastfm_tags(name: str, mbid: str | None, api_key: str | None = None, client: httpx.Client | None = None) -> list[str]:
    """The Band's top Last.fm tags as genres (see the module docstring); [] when there are none."""
    api_key = api_key if api_key is not None else settings.lastfm_api_key
    if not api_key:
        return []
    own_client = client is None
    client = client or httpx.Client(timeout=20, headers={"User-Agent": _USER_AGENT})
    try:
        artist = _get_info(client, api_key, mbid=mbid) if mbid else None
        if artist is None:
            artist = _get_info(client, api_key, artist=name, autocorrect="0")
            # A same-named artist Last.fm ties to another MusicBrainz id is a namesake, not our Band.
            if artist is not None and mbid and artist.get("mbid") and artist["mbid"] != mbid:
                return []
        if artist is None:
            return []
        raw = (artist.get("tags") or {}).get("tag") or []
        tags = [t.get("name", "").strip().lower() for t in ([raw] if isinstance(raw, dict) else raw)]
        return list(dict.fromkeys(t for t in tags if t and t not in _NOT_GENRES))[:MAX_TAGS]
    except Exception:
        logger.info("lastfm: no tags for %s", name, exc_info=True)
        return []
    finally:
        if own_client:
            client.close()


def lastfm_key_problem(api_key: str | None = None, client: httpx.Client | None = None) -> str | None:
    """Why Last.fm won't take the API key (missing, invalid, suspended), or None when it does. lastfm_tags turns a
    rejected key into no tags like any failure, so a long run checks first rather than missing every Band's tags."""
    api_key = api_key if api_key is not None else settings.lastfm_api_key
    if not api_key:
        return "LASTFM_API_KEY isn't set"
    own_client = client is None
    client = client or httpx.Client(timeout=20, headers={"User-Agent": _USER_AGENT})
    try:
        response = client.get(_API, params={"method": "artist.getinfo", "api_key": api_key, "format": "json",
                                            "artist": "Cher"})
        data = response.json()
        if "error" in data and data["error"] != _NOT_FOUND:
            return f"Last.fm rejected LASTFM_API_KEY (error {data['error']}: {data.get('message')})"
        response.raise_for_status()
        return None
    except Exception as e:
        return f"couldn't check LASTFM_API_KEY with Last.fm: {e}"
    finally:
        if own_client:
            client.close()
