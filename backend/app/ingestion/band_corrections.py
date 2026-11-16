"""Bands the services get wrong, put right by hand.

A Band is found on the services by its name, and its name can belong to other artists too: Sunblind, the Oakland
hardcore band, shares its name with a German trance act on MusicBrainz, Last.fm and Discogs and with a Philadelphia
band on Bandcamp. Most namesakes are caught by the rules (app/pipeline/enrichment.py _mb_search); a correction is
for one that isn't.

A correction can name the Band's MusicBrainz artist (looked up by its id rather than its name), or say that no
service is to match it by name (its name there is a namesake's). Its genres and links are used when the services
have none, so the order is: the services, then the correction. (The List itself only names a Band.)

Corrections are keyed by the Band's Slug (app/slugs.py), so the same Band spelled another way finds its own.
After adding one for a Band already stored, look it up again: `python -m app.cli backfill --redo "<name>"`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.slugs import slugify


@dataclass(frozen=True)
class BandCorrection:
    mbid: str | None = None          # its MusicBrainz artist, when a search by name can't find it
    by_name: bool = True             # False: its name is a namesake's on the services; never match it by name
    genres: tuple[str, ...] = ()     # its genres, when no service has any
    links: dict[str, str] = field(default_factory=dict)   # e.g. {"bandcamp_url": ...}, when MusicBrainz has no such link


CORRECTIONS: dict[str, BandCorrection] = {
    # Oakland hardcore (https://noecho.net/features/sunblind-hardcore-band-interview). Not on MusicBrainz, Last.fm or
    # Discogs as of October 2026; "Sunblind" there is a German trance act (MusicBrainz c75c82be-3a0e-4327-be53-
    # f14bfeac5fd0, Discogs 70254) and an Indonesian artist; sunblind.bandcamp.com is a Philadelphia band.
    "sunblind": BandCorrection(by_name=False, genres=("hardcore punk",),
                               links={"bandcamp_url": "https://sunblindhc.bandcamp.com/"}),
}


def band_correction(name: str) -> BandCorrection | None:
    """The correction for the Band with this name, or None."""
    return CORRECTIONS.get(slugify(name))


def corrected(name: str, enrichment: dict) -> dict:
    """A listed Band's data before the services are asked (app/ingestion/steve_list.py: no genres, no links), with
    its correction's genres and links; `enrichment` itself when it has no correction."""
    correction = band_correction(name)
    if correction is None:
        return enrichment
    corrected = {**enrichment, **correction.links}
    if correction.genres:
        corrected["genres"] = list(correction.genres)
    return corrected
