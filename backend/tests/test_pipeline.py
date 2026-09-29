"""Tests for T6: Gmail fetch, embedding helpers, full pipeline, maintenance, mutation."""
from __future__ import annotations

import base64
import quopri
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.config import settings
from app.ingestion.gmail import fetch_latest_list_email
from app.models.band import Band
from app.models.show import Show, ShowStatus
from app.models.venue import Region, Venue
from app.pipeline.embed import batch_embed_and_index, embed_and_index_band, embed_and_index_show
from app.scheduler import _run_ingestion_async, run_daily_maintenance

# ── sample data ───────────────────────────────────────────────────────────────

# Minimal two-show email (matches the parser's expected format)
_SAMPLE_BODY = """\
the list 2026

sep 25 fri
Deafheaven / Uniform
at Bottom of the Hill, SF a/a $15 8pm

oct  1 thr
Mdou Moctar
at The Chapel, SF 18+ $25/$28 8pm
"""

_FAKE_VEC = np.zeros(768, dtype=np.float32)


def _b64_qp(text: str) -> str:
    """Encode text as quoted-printable then base64url (mirrors Gmail API body.data)."""
    qp = quopri.encodestring(text.encode("utf-8"))
    return base64.urlsafe_b64encode(qp).decode("ascii")


async def _passthrough_enrich(raw):
    """Minimal enrich_show stand-in that copies all RawShow fields verbatim."""
    return {
        "date": raw.date,
        "bands": raw.bands,
        "venue_name": raw.venue_name,
        "city": raw.city,
        "door_time": raw.door_time,
        "set_time": raw.set_time,
        "price_raw": raw.price_raw,
        "age_restriction": raw.age_restriction,
        "status": raw.status,
        "is_recommended": raw.is_recommended,
        "will_sell_out": raw.will_sell_out,
        "is_pit": raw.is_pit,
        "is_drink_tickets": raw.is_drink_tickets,
        "is_no_reentry": raw.is_no_reentry,
        "notes": raw.notes,
        "raw_text": raw.raw_text,
        "genres": [],
        "spotify_url": None,
        "soundcloud_url": None,
        "venue_website": None,
        "address": None,
        "latitude": None,
        "longitude": None,
        "google_place_id": None,
        "ticket_url": None,
    }


# ── Gmail fetch ───────────────────────────────────────────────────────────────

@patch("app.ingestion.gmail.get_gmail_service")
def test_fetch_returns_decoded_body(mock_svc):
    svc = MagicMock()
    mock_svc.return_value = svc
    svc.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "msg1"}]
    }
    svc.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "Content-Transfer-Encoding", "value": "quoted-printable"}],
            "body": {"data": _b64_qp("the list 2026\n\nsep 25 fri")},
        }
    }
    text, meta = fetch_latest_list_email()
    assert text is not None
    assert "the list 2026" in text
    assert "sep 25 fri" in text


@patch("app.ingestion.gmail.get_gmail_service")
def test_fetch_returns_none_when_no_messages(mock_svc):
    svc = MagicMock()
    mock_svc.return_value = svc
    svc.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": []
    }
    text, meta = fetch_latest_list_email()
    assert text is None
    assert meta is None


@patch("app.ingestion.gmail.get_gmail_service")
def test_fetch_finds_plaintext_in_multipart(mock_svc):
    svc = MagicMock()
    mock_svc.return_value = svc
    svc.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "msg1"}]
    }
    svc.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "headers": [
                        {"name": "Content-Transfer-Encoding", "value": "quoted-printable"}
                    ],
                    "body": {"data": _b64_qp("plain text body")},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": _b64_qp("<html>html body</html>")},
                },
            ],
        }
    }
    text, meta = fetch_latest_list_email()
    assert text == "plain text body"


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

_SAMPLE_FETCH = (_SAMPLE_BODY, {"email_received_at": None, "email_subject": "the list 2026", "email_message_id": None})

@patch("app.scheduler.fetch_latest_list_email", return_value=_SAMPLE_FETCH)
@patch("app.scheduler.enrich_show", new_callable=AsyncMock)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_creates_shows_and_bands(mock_batch, mock_enrich, mock_fetch, db):
    mock_enrich.side_effect = _passthrough_enrich

    await _run_ingestion_async(db=db)

    assert db.query(Show).count() == 2
    assert db.query(Band).count() >= 2  # Deafheaven + Mdou Moctar (+ Uniform)
    mock_batch.assert_called_once()


@patch("app.scheduler.fetch_latest_list_email", return_value=_SAMPLE_FETCH)
@patch("app.scheduler.enrich_show", new_callable=AsyncMock)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_idempotent(mock_batch, mock_enrich, mock_fetch, db):
    mock_enrich.side_effect = _passthrough_enrich
    await _run_ingestion_async(db=db)
    show_count = db.query(Show).count()
    band_count = db.query(Band).count()

    mock_enrich.side_effect = _passthrough_enrich
    await _run_ingestion_async(db=db)

    assert db.query(Show).count() == show_count
    assert db.query(Band).count() == band_count


@patch("app.scheduler.fetch_latest_list_email", return_value=(None, None))
async def test_pipeline_returns_early_when_no_email(mock_fetch, db):
    await _run_ingestion_async(db=db)
    assert db.query(Show).count() == 0


@patch("app.scheduler.fetch_latest_list_email", return_value=_SAMPLE_FETCH)
@patch("app.scheduler.enrich_show", new_callable=AsyncMock)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_skips_enrichment_for_known_bands(mock_batch, mock_enrich, mock_fetch, db):
    """Second run should not call enrich_show for headliners already in the DB."""
    mock_enrich.side_effect = _passthrough_enrich
    await _run_ingestion_async(db=db)
    first_run_calls = mock_enrich.call_count

    mock_enrich.reset_mock()
    mock_enrich.side_effect = _passthrough_enrich
    await _run_ingestion_async(db=db)

    assert mock_enrich.call_count < first_run_calls


@patch("app.scheduler.fetch_latest_list_email", return_value=_SAMPLE_FETCH)
@patch("app.scheduler.enrich_show", new_callable=AsyncMock)
@patch("app.pipeline.embed.save_index")
@patch("app.pipeline.embed.upsert_vector")
@patch("app.pipeline.embed.load_or_create_index")
@patch("app.pipeline.embed.embed", new_callable=AsyncMock)
async def test_faiss_indices_saved(
    mock_embed, mock_load, mock_upsert_v, mock_save, mock_enrich, mock_fetch, db
):
    mock_embed.return_value = _FAKE_VEC
    mock_load.return_value = MagicMock()
    mock_enrich.side_effect = _passthrough_enrich

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
    today = date.today()
    _seed_show(db, today - timedelta(days=1), ShowStatus.upcoming)
    _seed_show(db, today + timedelta(days=1), ShowStatus.upcoming)
    db.commit()

    run_daily_maintenance(db=db)

    db.expire_all()
    statuses = {s.date: s.status for s in db.query(Show).all()}
    assert statuses[today - timedelta(days=1)] == ShowStatus.past
    assert statuses[today + timedelta(days=1)] == ShowStatus.upcoming


def test_maintenance_hard_deletes_old_shows(db):
    today = date.today()
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
