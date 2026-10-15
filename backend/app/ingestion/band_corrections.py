"""Bands the services and the edition get wrong, put right by hand.

A Band is found on the services by its name, and its name can belong to other artists too: Sunblind, the Oakland
hardcore band, shares its name with a German trance act on MusicBrainz, Last.fm and Discogs and with a Philadelphia
band on Bandcamp, whose page the edition links. Most namesakes are caught by the rules (app/pipeline/enrichment.py
_mb_search); a correction is for one that isn't, or where the edition is wrong too.

A correction can name the Band's MusicBrainz artist (looked up by its id rather than its name), or say that no
service is to match it by name (its name there is a namesake's). Its genres and links take the edition's place, so
the order is: the services, then the correction, then the edition.

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
    genres: tuple[str, ...] = ()     # its genres, in place of the edition's
    links: dict[str, str] = field(default_factory=dict)   # e.g. {"bandcamp_url": ...}, in place of the edition's


CORRECTIONS: dict[str, BandCorrection] = {
    # Oakland hardcore (https://noecho.net/features/sunblind-hardcore-band-interview). Not on MusicBrainz, Last.fm or
    # Discogs as of October 2026; "Sunblind" there is a German trance act (MusicBrainz c75c82be-3a0e-4327-be53-
    # f14bfeac5fd0, Discogs 70254) and an Indonesian artist. The edition links sunblind.bandcamp.com, a
    # Philadelphia band, and calls it indie rock.
    "sunblind": BandCorrection(by_name=False, genres=("hardcore punk",),
                               links={"bandcamp_url": "https://sunblindhc.bandcamp.com/"}),
}


def band_correction(name: str) -> BandCorrection | None:
    """The correction for the Band with this name, or None."""
    return CORRECTIONS.get(slugify(name))


def correct_edition(name: str, enrichment: dict) -> dict:
    """The edition's data for a Band (app/ingestion/edition.py), with its correction's genres and links in place of
    the edition's; `enrichment` itself when it has no correction."""
    correction = band_correction(name)
    if correction is None:
        return enrichment
    corrected = {**enrichment, **correction.links}
    if correction.genres:
        corrected["genres"] = list(correction.genres)
    return corrected
