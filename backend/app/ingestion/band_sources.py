"""The order a Band's data is taken from its sources, shared by the ingest (new Bands) and the backfill (existing
Bands) so the two can't drift apart. The services come first; the edition (or, in the backfill, what the Band
already has, mostly edition data) is only ever the last fallback.

Genres: MusicBrainz's curated genres, else Last.fm's tags, else Discogs' genres and styles, else MusicBrainz's
free-form tags, else the edition's. Photos: Wikimedia Commons, else Discogs, else the edition's.
"""
from __future__ import annotations

from collections.abc import Callable

from app.ingestion.discogs import DiscogsArtist, discogs_credit
from app.ingestion.wikimedia import CommonsPhoto


def service_genres(name: str, found: dict, lastfm: Callable[[str, str | None], list[str]],
                   discogs: Callable[[int], list[str]]) -> list[str]:
    """A Band's genres from the services, in order; [] when none has any (the caller falls back to the edition).

    `found` is its MusicBrainz lookup (with its Discogs artist under "discogs"). Last.fm and Discogs are asked only
    when what comes before them has nothing; `lastfm` and `discogs` are the lookups to use.
    """
    if found.get("mb_genres"):
        return found["genres"]
    if tags := lastfm(name, found.get("mbid")):
        return tags
    artist = found.get("discogs")
    return (discogs(artist.id) if artist else []) or found.get("genres") or []


def photo_candidates(commons: CommonsPhoto | None, artist: DiscogsArtist | None,
                     fallback_url: str | None) -> list[dict]:
    """A Band's photos in order, each {"url", "credit"}: Commons, Discogs, then `fallback_url` (the edition's, with no
    credit). Empty when no service has one: the caller then just keeps the edition's."""
    candidates = []
    if commons:
        candidates.append({"url": commons.url, "credit": commons.credit})
    if artist and artist.image_url:
        candidates.append({"url": artist.image_url, "credit": discogs_credit(artist)})
    if candidates and fallback_url:
        candidates.append({"url": fallback_url, "credit": None})
    return candidates
