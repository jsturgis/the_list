"""The order a Band's data is taken from its sources, shared by the ingest (new Bands) and the backfill (existing
Bands) so the two can't drift apart. The services come first; the edition (or, in the backfill, what the Band
already has, mostly edition data) is only ever the last fallback.

Genres: MusicBrainz's curated genres, else Last.fm's tags, else Discogs' genres and styles, else MusicBrainz's
free-form tags, else the edition's; only ever those that are genres
(app/ingestion/genre_filter.py). Photos: Wikimedia Commons, else Discogs, else the edition's.

A Band whose name MusicBrainz knows several artists by, and can't tell which is the Band, has namesakes: it's
matched on the other services only through MusicBrainz's links (it has none then), never by name, since their
same-named artist is as likely to be a namesake. A correction (app/ingestion/band_corrections.py) takes the
edition's place.
"""
from __future__ import annotations

from collections.abc import Callable

from app.ingestion.discogs import DiscogsArtist, discogs_credit
from app.ingestion.wikimedia import CommonsPhoto


def service_genres(name: str, found: dict, lastfm: Callable[[str, str | None], list[str]],
                   discogs: Callable[[int], list[str]],
                   keep: Callable[[list[str]], list[str]] = lambda tags: tags) -> list[str]:
    """A Band's genres from the services, in order; [] when none has any (the caller falls back to the edition).

    `found` is its MusicBrainz lookup (with its Discogs artist under "discogs"). Last.fm and Discogs are asked only
    when what comes before them has nothing; `lastfm` and `discogs` are the lookups to use. `keep` picks the genres
    among them (GenreFilter.keep), so a source with only tags that aren't genres counts as having none.
    MusicBrainz's curated genres are its genre list, so they always are.

    A Band with namesakes (found["namesakes"], see _enrich_band) isn't looked up on Last.fm, whose page for a name
    is every artist with it.
    """
    if found.get("mb_genres"):
        return found["genres"]
    if not found.get("namesakes") and (tags := keep(lastfm(name, found.get("mbid")))):
        return tags
    artist = found.get("discogs")
    return (keep(discogs(artist.id)) if artist else []) or keep(found.get("genres") or [])


def discogs_match(name: str, found: dict,
                  discogs: Callable[[str, list[dict]], DiscogsArtist | None]) -> DiscogsArtist | None:
    """The Band's Discogs artist through `discogs` (discogs_artist), by its MusicBrainz link or else its name; None
    for a Band with namesakes, which has no MusicBrainz links and isn't matched by name."""
    return None if found.get("namesakes") else discogs(name, found.get("links") or [])


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
