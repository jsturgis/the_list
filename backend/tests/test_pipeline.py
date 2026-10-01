"""Tests for embedding helpers, the edition ingestion pipeline, maintenance and venue re-enrichment."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.config import settings
from app.models.band import Band
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.models.show import Show, ShowStatus
from app.models.venue import Region, Venue
from app.pipeline.embed import batch_embed_and_index, embed_and_index_band, embed_and_index_show
from app.clock import local_today
from app.scheduler import _run_ingestion_async, run_daily_maintenance

# ── sample data ───────────────────────────────────────────────────────────────

_FAKE_VEC = np.zeros(768, dtype=np.float32)


# ── embedding helpers ─────────────────────────────────────────────────────────

@patch("app.pipeline.embed.save_index")
@patch("app.pipeline.embed.upsert_vector")
@patch("app.pipeline.embed.load_or_create_index")
@patch("app.pipeline.embed.embed", new_callable=AsyncMock)
async def test_embed_and_index_band_stores_bytes(
    mock_embed, mock_load, mock_upsert, mock_save, db
):
    mock_embed.return_value = _FAKE_VEC
    mock_load.return_value = MagicMock()

    band = Band(name="Deafheaven", genres=["black metal", "shoegaze"])
    db.add(band)
    db.flush()

    await embed_and_index_band(db, band)

    assert band.embedding == _FAKE_VEC.tobytes()
    mock_upsert.assert_called_once()
    mock_save.assert_called_once()


@patch("app.pipeline.embed.save_index")
@patch("app.pipeline.embed.upsert_vector")
@patch("app.pipeline.embed.load_or_create_index")
@patch("app.pipeline.embed.embed", new_callable=AsyncMock)
async def test_embed_and_index_show_stores_bytes(
    mock_embed, mock_load, mock_upsert, mock_save, db
):
    from app.models.act import Act

    mock_embed.return_value = _FAKE_VEC
    mock_load.return_value = MagicMock()

    venue = Venue(name="The Fillmore", city="San Francisco", region=Region.sf)
    db.add(venue)
    db.flush()
    show = Show(date=date(2026, 9, 25), venue_id=venue.id, status=ShowStatus.upcoming)
    db.add(show)
    db.flush()
    band = Band(name="Deafheaven", genres=["black metal"])
    db.add(band)
    db.flush()
    db.add(Act(show_id=show.id, band_id=band.id, position=0))
    db.flush()

    # Reload with relationships
    from sqlalchemy.orm import joinedload
    show = (
        db.query(Show)
        .options(joinedload(Show.venue), joinedload(Show.acts).joinedload(Act.band))
        .filter(Show.id == show.id)
        .one()
    )

    await embed_and_index_show(db, show)

    assert show.embedding == _FAKE_VEC.tobytes()
    mock_upsert.assert_called_once()
    mock_save.assert_called_once()


# ── full pipeline ─────────────────────────────────────────────────────────────

def _edition_event(date_, venue, city, artists, details, age="all_ages"):
    """A schema v2.0.0 event."""
    return {"event_id": f"{date_}-{venue}", "date": date_, "day_of_week": "", "status": "scheduled",
            "age_restriction": age, "list_flags": [], "doors_time": None, "show_time": None, "ticketing": {},
            "venue": {"name": venue, "address": f"1 Main St, {city}", "region": "San Francisco Venues",
                      "url": f"https://{venue.lower().replace(' ', '')}.com/", "coordinates": None},
            "artists": [{"name": n, "role": "headliner" if i == 0 else "support", "genre": g, "url": u}
                        for i, (n, g, u) in enumerate(artists)],
            "raw_details": details}


_EDITION = {
    "title": "Bay Area & Santa Cruz Concert Events", "edition_date": "2026-09-25", "schema_version": "2.0.0",
    "events": [
        _edition_event("Sep 25, 2026", "Bottom of the Hill", "San Francisco",
                       [("Deafheaven", "Blackgaze", "https://deafheaven.bandcamp.com/"), ("Uniform", "Noise Rock", "")],
                       "a/a $15 8pm"),
        _edition_event("Oct 1, 2026", "The Chapel", "San Francisco",
                       [("Mdou Moctar", "Tuareg Rock / Psych", "")], "18+ $25/$28 8pm", age="18+"),
    ],
}
_SAMPLE_FETCH = (_EDITION, {"file_id": "edition-file-id", "file_name": "Concert Events - September 25, 2026.json"})


def _venue_data(name, city, street=None, use_llm=True):
    """Google Places stand-in: a distinct place per Venue."""
    return {"address": f"{street}, {city}, CA, USA", "google_place_id": f"ChIJ-{name}", "city": city}


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_imports_the_edition(mock_batch, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    assert db.query(Show).count() == 2
    deafheaven = db.query(Band).filter(Band.name == "Deafheaven").one()
    assert deafheaven.genres == ["blackgaze"]
    assert deafheaven.bandcamp_url == "https://deafheaven.bandcamp.com/"
    assert {b.name for b in db.query(Band)} == {"Deafheaven", "Uniform", "Mdou Moctar"}
    chapel = db.query(Venue).filter(Venue.name == "The Chapel").one()
    assert chapel.google_place_id == "ChIJ-The Chapel"
    assert chapel.website_url == "https://thechapel.com/"
    mock_batch.assert_called_once()


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_records_the_ingestion_run(mock_batch, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    run = db.query(IngestionRun).one()
    assert run.status == IngestionStatus.success
    assert run.email_subject == "Bay Area & Santa Cruz Concert Events — Sep 25, 2026"
    assert run.email_message_id == "edition-file-id"
    assert run.email_received_at.date() == date(2026, 9, 25)
    assert (run.shows_parsed, run.shows_upserted, run.shows_new) == (2, 2, 2)


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_idempotent_and_enriches_only_new_venues(mock_batch, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)
    assert mock_venue.call_count == 2
    counts = (db.query(Show).count(), db.query(Band).count(), db.query(Venue).count())

    mock_venue.reset_mock()
    await _run_ingestion_async(db=db)

    assert (db.query(Show).count(), db.query(Band).count(), db.query(Venue).count()) == counts
    mock_venue.assert_not_called()
    assert db.query(IngestionRun).order_by(IngestionRun.id.desc()).first().shows_new == 0


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_makes_no_llm_calls(mock_batch, mock_venue, mock_fetch, db):
    """Edition names are already clean, so venue enrichment runs without the LLM."""
    with patch("app.pipeline.enrichment.get_enrichment_llm") as llm:
        await _run_ingestion_async(db=db)
    llm.assert_not_called()
    assert mock_venue.call_count == 2
    assert all(call.args[3] is False for call in mock_venue.call_args_list)  # use_llm=False


_NO_GENRE_EDITION = {
    **_EDITION,
    "events": _EDITION["events"] + [
        _edition_event("Oct 2, 2026", "Bottom of the Hill", "San Francisco",
                       [("Chat Pile", "", ""), ("Deafheaven", "Blackgaze", ""), ("Mystery Act", "", "")], "21+ $20 9pm"),
        _edition_event("Oct 3, 2026", "The Chapel", "San Francisco", [("Chat Pile", "", "")], "21+ $20 9pm"),
    ],
}


def _musicbrainz(name, use_llm=True):
    found = {"Chat Pile": {"genres": ["noise rock", "sludge metal"], "spotify_url": None, "soundcloud_url": None,
                           "bandcamp_url": "https://chatpile.bandcamp.com/"}}
    return found.get(name, {"genres": [], "spotify_url": None, "soundcloud_url": None, "bandcamp_url": None})


@patch("app.scheduler.fetch_latest_edition", return_value=(_NO_GENRE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_musicbrainz)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_looks_up_genres_for_bands_without_one(mock_batch, mock_band, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    chat_pile = db.query(Band).filter(Band.name == "Chat Pile").one()
    assert chat_pile.genres == ["noise rock", "sludge metal"]
    assert chat_pile.bandcamp_url == "https://chatpile.bandcamp.com/"
    assert db.query(Band).filter(Band.name == "Mystery Act").one().genres == []
    # Only Bands without a genre are looked up, once per name, and without the LLM.
    looked_up = sorted(call.args[0] for call in mock_band.call_args_list)
    assert looked_up == ["Chat Pile", "Mystery Act"]  # Uniform and Deafheaven arrive with genres
    assert all(call.args[1] is False for call in mock_band.call_args_list)


@patch("app.scheduler.fetch_latest_edition", return_value=(_NO_GENRE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_musicbrainz)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_skips_lookup_for_bands_already_known_with_genres(mock_batch, mock_band, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)
    mock_band.reset_mock()

    await _run_ingestion_async(db=db)

    # Chat Pile now has genres; only the still-unknown Bands are tried again.
    assert [call.args[0] for call in mock_band.call_args_list] == ["Mystery Act"]


@patch("app.scheduler.fetch_latest_edition", return_value=(None, None))
async def test_pipeline_returns_early_when_no_edition(mock_fetch, db):
    await _run_ingestion_async(db=db)
    assert db.query(Show).count() == 0
    assert db.query(IngestionRun).one().status == IngestionStatus.no_email


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", return_value={})
@patch("app.pipeline.embed.save_index")
@patch("app.pipeline.embed.upsert_vector")
@patch("app.pipeline.embed.load_or_create_index")
@patch("app.pipeline.embed.embed", new_callable=AsyncMock)
async def test_faiss_indices_saved(
    mock_embed, mock_load, mock_upsert_v, mock_save, mock_venue, mock_fetch, db
):
    mock_embed.return_value = _FAKE_VEC
    mock_load.return_value = MagicMock()

    await _run_ingestion_async(db=db)

    assert mock_save.call_count == 2  # exactly one save per index type


# ── daily maintenance ─────────────────────────────────────────────────────────

def _seed_show(db, show_date, status=ShowStatus.upcoming):
    v = db.query(Venue).first()
    if not v:
        v = Venue(name="Test Venue", city="SF", region=Region.sf)
        db.add(v)
        db.flush()
    s = Show(date=show_date, venue_id=v.id, status=status)
    db.add(s)
    db.flush()
    return s


def test_maintenance_marks_past_shows(db):
    today = local_today()
    _seed_show(db, today - timedelta(days=1), ShowStatus.upcoming)
    _seed_show(db, today + timedelta(days=1), ShowStatus.upcoming)
    db.commit()

    run_daily_maintenance(db=db)

    db.expire_all()
    statuses = {s.date: s.status for s in db.query(Show).all()}
    assert statuses[today - timedelta(days=1)] == ShowStatus.past
    assert statuses[today + timedelta(days=1)] == ShowStatus.upcoming


def test_maintenance_hard_deletes_old_shows(db):
    today = local_today()
    old_date = today - timedelta(days=settings.data_retention_days + 1)
    recent_date = today - timedelta(days=1)
    _seed_show(db, old_date, ShowStatus.past)
    _seed_show(db, recent_date, ShowStatus.upcoming)
    db.commit()

    run_daily_maintenance(db=db)

    db.expire_all()
    dates = [s.date for s in db.query(Show).all()]
    assert old_date not in dates
    assert recent_date in dates


# ── startIngestion mutation ───────────────────────────────────────────────────

@patch("app.graphql.mutations.asyncio.create_task")
def test_start_ingestion_mutation(mock_create_task, client):
    resp = client.post("/graphql", json={"query": "mutation { startIngestion }"})
    assert resp.status_code == 200
    body = resp.json()
    assert "errors" not in body
    assert body["data"]["startIngestion"] == "ingestion started"
    mock_create_task.assert_called_once()


# ── venue re-enrichment ───────────────────────────────────────────────────────

async def test_venue_enrichment_keeps_region_when_google_returns_a_neighbourhood(db):
    from app.scheduler import _run_venue_enrichment_async

    venue = Venue(name="Starry Plough", city="Berkeley", region=Region.east_bay)
    db.add(venue)
    db.commit()
    venue_id = venue.id  # the function closes its session, detaching `venue`
    enrich = MagicMock(return_value={"address": "3101 Shattuck Ave", "city": "Temescal"})

    with patch("app.scheduler.SessionLocal", return_value=db), \
         patch("app.scheduler._enrich_venue", enrich), \
         patch("app.scheduler._clean_venue_name", MagicMock()):
        await _run_venue_enrichment_async(venue_id)

    refreshed = db.get(Venue, venue_id)
    assert refreshed.city == "Temescal"
    assert refreshed.region == Region.east_bay  # not moved to the "sf" default


_IMAGE_EDITION = {
    **_EDITION,
    "events": [{**_EDITION["events"][0],
                "venue": {**_EDITION["events"][0]["venue"], "image_url": "https://example.com/made-up-venue.jpg"},
                "artists": [{**_EDITION["events"][0]["artists"][0], "image_url": "https://example.com/wrong-path.jpg"},
                            _EDITION["events"][0]["artists"][1]]}],
}


@patch("app.scheduler.fetch_latest_edition", return_value=(_IMAGE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.check_image_urls", return_value={
    "https://example.com/made-up-venue.jpg": None,
    "https://example.com/wrong-path.jpg": "https://example.com/real-path.jpg",
})
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_saves_only_images_that_load(mock_batch, mock_images, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    assert db.query(Band).filter(Band.name == "Deafheaven").one().image_url == "https://example.com/real-path.jpg"
    assert db.query(Venue).filter(Venue.name == "Bottom of the Hill").one().image_url is None
    assert sorted(mock_images.call_args.args[0]) == ["https://example.com/made-up-venue.jpg", "https://example.com/wrong-path.jpg"]
