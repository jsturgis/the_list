"""Tests for the per-ingest stats on new Bands: how many have no photo, and how many fell back to the edition."""
from __future__ import annotations

from app.ingestion.ingest_stats import new_band_stats
from app.models.band import Band

_CREDIT = {"author": "A", "license": "CC BY 4.0", "license_url": None, "source_url": "https://c/x"}


def _band(name, *, image_url=None, image_credit=None, genres=(), **links):
    return Band(name=name, image_url=image_url, image_credit=image_credit, genres=list(genres), **links)


def test_percentages_of_new_bands():
    bands = [
        _band("Commons", image_url="bands/1-a.webp", image_credit=_CREDIT, genres=["noise rock"],
              spotify_url="https://open.spotify.com/artist/mb"),
        _band("Edition photo", image_url="bands/2-b.webp", genres=["punk"], bandcamp_url="https://x.bandcamp.com/"),
        _band("No photo", genres=["jazz"]),
        _band("Nothing"),
    ]
    stats = new_band_stats(
        bands,
        edition_genres={"Edition photo": ["punk"]},                        # its genres came from the edition
        edition_links={"Edition photo": {"bandcamp_url": "https://x.bandcamp.com/"},
                       "No photo": {"website_url": "https://dropped.example/"}},  # dropped later: doesn't count
    )
    assert stats == {
        "new_bands": 4,
        "new_bands_without_photo_pct": 50.0,         # No photo, Nothing
        "new_bands_photo_from_edition_pct": 25.0,    # Edition photo (stored, no credit)
        "new_bands_genres_from_edition_pct": 25.0,
        "new_bands_links_from_edition_pct": 25.0,
    }


def test_no_new_bands_means_no_percentages():
    assert new_band_stats([], {}, {}) == {
        "new_bands": 0, "new_bands_without_photo_pct": None, "new_bands_photo_from_edition_pct": None,
        "new_bands_genres_from_edition_pct": None, "new_bands_links_from_edition_pct": None,
    }


def test_percentages_are_rounded_to_one_decimal():
    bands = [_band("A"), _band("B", image_url="bands/1.webp", image_credit=_CREDIT), _band("C", image_url="u", image_credit=_CREDIT)]
    assert new_band_stats(bands, {}, {})["new_bands_without_photo_pct"] == 33.3


def test_genres_a_service_gave_that_match_nothing_recorded_dont_count():
    bands = [_band("Service genres", genres=["punk"])]
    assert new_band_stats(bands, edition_genres={}, edition_links={})["new_bands_genres_from_edition_pct"] == 0.0
