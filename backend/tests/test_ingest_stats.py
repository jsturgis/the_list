"""Tests for the per-ingest stats on new Bands: how many there are, and how many have no photo."""
from __future__ import annotations

from app.ingestion.ingest_stats import new_band_stats
from app.models.band import Band

_CREDIT = {"author": "A", "license": "CC BY 4.0", "license_url": None, "source_url": "https://c/x"}


def _band(name, *, image_url=None, image_credit=None):
    return Band(name=name, image_url=image_url, image_credit=image_credit)


def test_share_of_new_bands_without_a_photo():
    bands = [_band("Commons", image_url="bands/1-a.webp", image_credit=_CREDIT),
             _band("Discogs", image_url="bands/2-b.webp", image_credit=_CREDIT),
             _band("No photo"), _band("Nothing")]
    assert new_band_stats(bands) == {"new_bands": 4, "new_bands_without_photo_pct": 50.0}


def test_no_new_bands_means_no_percentage():
    assert new_band_stats([]) == {"new_bands": 0, "new_bands_without_photo_pct": None}


def test_the_percentage_is_rounded_to_one_decimal():
    bands = [_band("A"), _band("B", image_url="bands/1.webp", image_credit=_CREDIT), _band("C", image_url="u", image_credit=_CREDIT)]
    assert new_band_stats(bands)["new_bands_without_photo_pct"] == 33.3
