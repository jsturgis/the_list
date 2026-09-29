"""Tests for enrich_show — all external calls mocked."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.parser import RawShow
from app.pipeline.enrichment import _enrich_venue, enrich_show


@pytest.fixture(autouse=True)
def clear_venue_cache():
    _enrich_venue.cache_clear()
    yield
    _enrich_venue.cache_clear()


# ── helpers ───────────────────────────────────────────────────────────────────

def _raw(
    *,
    bands: list[str] | None = None,
    venue_name: str = "The Fillmore",
    city: str = "S.F.",
    price_raw: str | None = "$25",
    status: str = "upcoming",
    **kwargs,
) -> RawShow:
    return RawShow(
        raw_text="raw",
        date=date(2026, 9, 25),
        bands=bands if bands is not None else ["Headliner", "Support"],
        venue_name=venue_name,
        city=city,
        price_raw=price_raw,
        status=status,
        **kwargs,
    )


def _mb_artist(mbid: str = "abc-123") -> dict:
    return {"id": mbid, "name": "Headliner"}


def _mb_full(
    tags: list[dict] | None = None,
    url_rels: list[dict] | None = None,
) -> dict:
    return {
        "tag-list": tags or [],
        "url-relation-list": url_rels or [],
    }


# ── passthrough fields ────────────────────────────────────────────────────────

@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment._mb_search", return_value=None)
async def test_passthrough_fields(mock_search, mock_venue):
    raw = _raw(bands=["Band A"], price_raw="$15", age_restriction="21+")
    result = await enrich_show(raw)
    assert result["date"] == date(2026, 9, 25)
    assert result["bands"] == ["Band A"]
    assert result["venue_name"] == "The Fillmore"
    assert result["city"] == "S.F."
    assert result["price_raw"] == "$15"
    assert result["age_restriction"] == "21+"
    assert result["status"] == "upcoming"


# ── MusicBrainz genres ────────────────────────────────────────────────────────

@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment.get_enrichment_llm")
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_mb_hit_genres_set_no_genre_llm(mock_search, mock_lookup, mock_llm, mock_venue):
    """LLM is only called for SoundCloud/Bandcamp fallback, not genre extraction when MB returns tags."""
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(tags=[
        {"name": "indie rock", "count": "10"},
        {"name": "shoegaze", "count": "7"},
    ])
    llm_instance = MagicMock()
    llm_instance.invoke.return_value = MagicMock(content="unknown")
    mock_llm.return_value = llm_instance
    result = await enrich_show(_raw())
    assert result["genres"] == ["indie rock", "shoegaze"]
    # LLM not used for genre extraction
    llm_instance.with_structured_output.assert_not_called()


@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_mb_top_5_tags_only(mock_search, mock_lookup, mock_venue):
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(tags=[
        {"name": "punk", "count": "20"},
        {"name": "hardcore", "count": "15"},
        {"name": "post-punk", "count": "12"},
        {"name": "indie", "count": "10"},
        {"name": "noise", "count": "8"},
        {"name": "metal", "count": "5"},
    ])
    result = await enrich_show(_raw())
    assert result["genres"] == ["punk", "hardcore", "post-punk", "indie", "noise"]
    assert len(result["genres"]) == 5


@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment._mb_search", return_value=None)
async def test_mb_no_result_genres_empty(mock_search, mock_venue):
    result = await enrich_show(_raw())
    assert result["genres"] == []


@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment.get_enrichment_llm")
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_mb_empty_tags_no_soundcloud_genres_empty(mock_search, mock_lookup, mock_llm, mock_venue):
    """Empty tags + no SoundCloud URL → genres = [] (LLM not used for genre extraction)."""
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(tags=[], url_rels=[])
    llm_instance = MagicMock()
    llm_instance.invoke.return_value = MagicMock(content="unknown")
    mock_llm.return_value = llm_instance
    result = await enrich_show(_raw())
    assert result["genres"] == []
    llm_instance.with_structured_output.assert_not_called()


@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment._scrape_text", return_value="electronic shoegaze music from SF")
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
@patch("app.pipeline.enrichment.get_enrichment_llm")
async def test_mb_empty_tags_with_soundcloud_calls_llm(mock_llm, mock_search, mock_lookup, mock_scrape, mock_venue):
    """Empty tags + SoundCloud URL available → scrape it → LLM extracts genres."""
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(
        tags=[],
        url_rels=[{"type": "social network", "target": "https://soundcloud.com/headliner"}],
    )
    llm_instance = MagicMock()
    llm_instance.with_structured_output.return_value.invoke.return_value = MagicMock(genres=["shoegaze", "electronic"])
    mock_llm.return_value = llm_instance

    result = await enrich_show(_raw())
    assert result["genres"] == ["shoegaze", "electronic"]
    llm_instance.with_structured_output.assert_called_once()


# ── SoundCloud LLM fallback ───────────────────────────────────────────────────

@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment.httpx.head")
@patch("app.pipeline.enrichment.get_enrichment_llm")
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_soundcloud_llm_fallback_verified(mock_search, mock_lookup, mock_llm, mock_head, mock_venue):
    """LLM suggests slug → HEAD verifies → soundcloud_url set."""
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(tags=[{"name": "indie", "count": "5"}], url_rels=[])
    llm_instance = MagicMock()
    llm_instance.invoke.return_value = MagicMock(content="headliner-band")
    mock_llm.return_value = llm_instance
    mock_head.return_value = MagicMock(status_code=200)

    result = await enrich_show(_raw())
    assert result["soundcloud_url"] == "https://soundcloud.com/headliner-band"


@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment.httpx.head")
@patch("app.pipeline.enrichment.get_enrichment_llm")
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_soundcloud_llm_fallback_404(mock_search, mock_lookup, mock_llm, mock_head, mock_venue):
    """LLM suggests slug → HEAD returns 404 → soundcloud_url stays None."""
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(tags=[{"name": "indie", "count": "5"}], url_rels=[])
    llm_instance = MagicMock()
    llm_instance.invoke.return_value = MagicMock(content="wrong-slug")
    mock_llm.return_value = llm_instance
    mock_head.return_value = MagicMock(status_code=404)

    result = await enrich_show(_raw())
    assert result["soundcloud_url"] is None


@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment.httpx.head")
@patch("app.pipeline.enrichment.get_enrichment_llm")
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_soundcloud_llm_fallback_unknown(mock_search, mock_lookup, mock_llm, mock_head, mock_venue):
    """LLM replies 'unknown' → no HEAD request → soundcloud_url stays None."""
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(tags=[{"name": "indie", "count": "5"}], url_rels=[])
    llm_instance = MagicMock()
    llm_instance.invoke.return_value = MagicMock(content="unknown")
    mock_llm.return_value = llm_instance

    result = await enrich_show(_raw())
    assert result["soundcloud_url"] is None
    mock_head.assert_not_called()


# ── MusicBrainz streaming URLs ────────────────────────────────────────────────

@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_mb_spotify_url_set(mock_search, mock_lookup, mock_venue):
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(
        tags=[{"name": "indie", "count": "5"}],
        url_rels=[{"type": "streaming music", "target": "https://open.spotify.com/artist/abc"}],
    )
    result = await enrich_show(_raw())
    assert result["spotify_url"] == "https://open.spotify.com/artist/abc"
    assert result["soundcloud_url"] is None


@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_mb_soundcloud_url_set(mock_search, mock_lookup, mock_venue):
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(
        tags=[{"name": "indie", "count": "5"}],
        url_rels=[{"type": "social network", "target": "https://soundcloud.com/headliner"}],
    )
    result = await enrich_show(_raw())
    assert result["soundcloud_url"] == "https://soundcloud.com/headliner"
    assert result["spotify_url"] is None


@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_mb_below_threshold_no_match(mock_search, mock_lookup, mock_venue):
    """Score below threshold → treated as no result."""
    mock_search.return_value = None  # _mb_search filters below threshold internally
    result = await enrich_show(_raw())
    assert result["genres"] == []
    assert result["spotify_url"] is None
    mock_lookup.assert_not_called()


# ── Google Maps venue enrichment ──────────────────────────────────────────────

@patch("app.pipeline.enrichment._search_wikipedia", return_value=None)
@patch("app.pipeline.enrichment._mb_search", return_value=None)
@patch("app.pipeline.enrichment.settings")
@patch("app.pipeline.enrichment.httpx.get")   # Timezone API
@patch("app.pipeline.enrichment.httpx.post")  # Places API
async def test_venue_maps_result_sets_fields(mock_post, mock_get, mock_settings, mock_mb, mock_wiki):
    mock_settings.google_maps_api_key = "fake-key"
    mock_settings.musicbrainz_app_name = "the-list"
    mock_settings.musicbrainz_app_version = "0.1"
    mock_settings.musicbrainz_contact = "test@example.com"
    mock_post.return_value.json.return_value = {
        "places": [{
            "formattedAddress": "1805 Geary Blvd, San Francisco, CA 94115",
            "websiteUri": "https://thefillmore.com",
            "location": {"latitude": 37.7842, "longitude": -122.4324},
            "id": "ChIJabc123",
            "nationalPhoneNumber": "(415) 346-3000",
            "rating": 4.7,
            "utcOffsetMinutes": -420,
        }]
    }
    mock_get.return_value.json.return_value = {"status": "OK", "timeZoneId": "America/Los_Angeles"}
    result = await enrich_show(_raw())
    assert result["address"] == "1805 Geary Blvd, San Francisco, CA 94115"
    assert result["venue_website"] == "https://thefillmore.com"
    assert result["latitude"] == pytest.approx(37.7842)
    assert result["longitude"] == pytest.approx(-122.4324)
    assert result["google_place_id"] == "ChIJabc123"
    assert result["phone"] == "(415) 346-3000"
    assert result["google_rating"] == pytest.approx(4.7)
    assert result["timezone"] == "America/Los_Angeles"
    assert result["venue_description"] is None
    assert result["venue_wikipedia_url"] is None


@patch("app.pipeline.enrichment._generate_venue_description", return_value="A historic SF music venue.")
@patch("app.pipeline.enrichment._fetch_wikipedia_data")
@patch("app.pipeline.enrichment._search_wikipedia", return_value="The Fillmore")
@patch("app.pipeline.enrichment._mb_search", return_value=None)
@patch("app.pipeline.enrichment.settings")
@patch("app.pipeline.enrichment.httpx.get")
@patch("app.pipeline.enrichment.httpx.post")
async def test_venue_wikipedia_description_and_url(mock_post, mock_get, mock_settings, mock_mb, mock_wiki_search, mock_wiki_data, mock_desc):
    """Wikipedia found → description generated, wikipedia_url set, website falls back to wiki if Google has none."""
    mock_settings.google_maps_api_key = "fake-key"
    mock_settings.musicbrainz_app_name = "the-list"
    mock_settings.musicbrainz_app_version = "0.1"
    mock_settings.musicbrainz_contact = "test@example.com"
    mock_post.return_value.json.return_value = {
        "places": [{
            "formattedAddress": "1805 Geary Blvd",
            "websiteUri": None,
            "location": {"latitude": 37.78, "longitude": -122.43},
            "id": "ChIJabc",
            "nationalPhoneNumber": None,
            "rating": None,
        }]
    }
    mock_get.return_value.json.return_value = {"status": "OK", "timeZoneId": "America/Los_Angeles"}
    mock_wiki_data.return_value = {
        "extract": "The Fillmore is a historic music venue...",
        "wikipedia_url": "https://en.wikipedia.org/wiki/The_Fillmore",
        "website_url": "https://thefillmore.com",
    }

    result = await enrich_show(_raw())
    assert result["venue_description"] == "A historic SF music venue."
    assert result["venue_wikipedia_url"] == "https://en.wikipedia.org/wiki/The_Fillmore"
    assert result["venue_website"] == "https://thefillmore.com"  # wiki fallback used


@patch("app.pipeline.enrichment._mb_search", return_value=None)
@patch("app.pipeline.enrichment.settings")
@patch("app.pipeline.enrichment.httpx.post")
async def test_venue_maps_no_result_fields_none(mock_post, mock_settings, mock_mb):
    mock_settings.google_maps_api_key = "fake-key"
    mock_settings.musicbrainz_app_name = "the-list"
    mock_settings.musicbrainz_app_version = "0.1"
    mock_settings.musicbrainz_contact = "test@example.com"
    mock_post.return_value.json.return_value = {"places": []}
    result = await enrich_show(_raw())
    assert result["address"] is None
    assert result["venue_website"] is None
    assert result["latitude"] is None
    assert result["longitude"] is None
    assert result["google_place_id"] is None


@patch("app.pipeline.enrichment._mb_search", return_value=None)
@patch("app.pipeline.enrichment.settings")
async def test_venue_maps_skipped_when_no_api_key(mock_settings, mock_mb):
    mock_settings.google_maps_api_key = ""
    mock_settings.musicbrainz_app_name = "the-list"
    mock_settings.musicbrainz_app_version = "0.1"
    mock_settings.musicbrainz_contact = "test@example.com"
    result = await enrich_show(_raw())
    assert result["address"] is None
    assert result["venue_website"] is None


# ── ticket URL ────────────────────────────────────────────────────────────────

# ── Bandcamp LLM fallback ────────────────────────────────────────────────────

@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment.httpx.head")
@patch("app.pipeline.enrichment.get_enrichment_llm")
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_bandcamp_llm_fallback_when_no_spotify_or_soundcloud(mock_search, mock_lookup, mock_llm, mock_head, mock_venue):
    """No spotify + no soundcloud → LLM suggests Bandcamp subdomain → verified → bandcamp_url set."""
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(tags=[{"name": "indie", "count": "5"}], url_rels=[])
    llm_instance = MagicMock()
    # First call: SoundCloud slug → "unknown"; second call: Bandcamp subdomain → "headlinerband"
    llm_instance.invoke.side_effect = [
        MagicMock(content="unknown"),          # SoundCloud fallback
        MagicMock(content="headlinerband"),    # Bandcamp fallback
    ]
    mock_llm.return_value = llm_instance
    mock_head.return_value = MagicMock(status_code=200)

    result = await enrich_show(_raw())
    assert result["bandcamp_url"] == "https://headlinerband.bandcamp.com"
    assert result["soundcloud_url"] is None
    assert result["spotify_url"] is None


@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment.httpx.head")
@patch("app.pipeline.enrichment.get_enrichment_llm")
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_bandcamp_skipped_when_soundcloud_found(mock_search, mock_lookup, mock_llm, mock_head, mock_venue):
    """SoundCloud found → Bandcamp LLM fallback not attempted."""
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(
        tags=[{"name": "indie", "count": "5"}],
        url_rels=[{"type": "social network", "target": "https://soundcloud.com/headliner"}],
    )
    mock_llm.return_value = MagicMock()

    result = await enrich_show(_raw())
    assert result["bandcamp_url"] is None
    assert result["soundcloud_url"] == "https://soundcloud.com/headliner"


@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment.httpx.head")
@patch("app.pipeline.enrichment.get_enrichment_llm")
@patch("app.pipeline.enrichment._mb_lookup")
@patch("app.pipeline.enrichment._mb_search")
async def test_bandcamp_llm_slug_with_dot_rejected(mock_search, mock_lookup, mock_llm, mock_head, mock_venue):
    """Slug containing a dot is rejected without HEAD request."""
    mock_search.return_value = _mb_artist()
    mock_lookup.return_value = _mb_full(tags=[{"name": "indie", "count": "5"}], url_rels=[])
    llm_instance = MagicMock()
    llm_instance.invoke.side_effect = [
        MagicMock(content="unknown"),               # SoundCloud fallback
        MagicMock(content="headliner.bandcamp"),    # invalid slug with dot
    ]
    mock_llm.return_value = llm_instance

    result = await enrich_show(_raw())
    assert result["bandcamp_url"] is None


# ── no bands ──────────────────────────────────────────────────────────────────

@patch("app.pipeline.enrichment._enrich_venue", return_value={})
@patch("app.pipeline.enrichment._mb_search")
async def test_no_bands_skips_mb(mock_search, mock_venue):
    result = await enrich_show(_raw(bands=[]))
    assert result["genres"] == []
    assert result["spotify_url"] is None
    mock_search.assert_not_called()
