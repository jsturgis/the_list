"""How an ingest's new Bands came out: how many there were, and the share no service had a photo for. Stored on the
ingestion run, so the lookups' coverage can be followed week to week.
"""
from __future__ import annotations

from app.models.band import Band


def new_band_stats(bands: list[Band]) -> dict:
    """Stats for the ingest's new Bands, as IngestionRun fields. The percentage is None when there are none."""
    total = len(bands)
    if total == 0:
        return {"new_bands": 0, "new_bands_without_photo_pct": None}
    without_photo = sum(not b.image_url for b in bands)
    return {"new_bands": total, "new_bands_without_photo_pct": round(100 * without_photo / total, 1)}
