"""How an ingest's new Bands came out: the share with no photo, and the share that had to fall back to the edition
(per field) because no service had anything. Stored on the ingestion run, so the lookups' coverage can be followed
week to week.

The ingest records which new Bands took their genres or links from the edition when it chooses them; whether that
survived (a link can be dropped as broken) is read from the Bands afterwards. A photo from a service always carries
a credit, so a stored photo without one is the edition's.
"""
from __future__ import annotations

from app.models.band import Band


def _pct(count: int, total: int) -> float:
    return round(100 * count / total, 1)


def new_band_stats(bands: list[Band], edition_genres: dict[str, list[str]],
                   edition_links: dict[str, dict[str, str]]) -> dict:
    """Stats for the ingest's new Bands, as IngestionRun fields. Percentages are None when there are none.

    `edition_genres` maps a Band's name to the edition genres it was given; `edition_links` maps it to the link
    fields (and URLs) it was given from the edition.
    """
    total = len(bands)
    if total == 0:
        return {"new_bands": 0, "new_bands_without_photo_pct": None, "new_bands_photo_from_edition_pct": None,
                "new_bands_genres_from_edition_pct": None, "new_bands_links_from_edition_pct": None}
    without_photo = sum(not b.image_url for b in bands)
    photo_from_edition = sum(bool(b.image_url) and not b.image_credit for b in bands)
    genres_from_edition = sum(bool(b.genres) and b.genres == edition_genres.get(b.name) for b in bands)
    links_from_edition = sum(any(getattr(b, field) == url for field, url in edition_links.get(b.name, {}).items())
                             for b in bands)
    return {
        "new_bands": total,
        "new_bands_without_photo_pct": _pct(without_photo, total),
        "new_bands_photo_from_edition_pct": _pct(photo_from_edition, total),
        "new_bands_genres_from_edition_pct": _pct(genres_from_edition, total),
        "new_bands_links_from_edition_pct": _pct(links_from_edition, total),
    }
