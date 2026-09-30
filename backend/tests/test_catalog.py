"""Tests for catalog read functions shared by the GraphQL API and the static export."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np

from app.catalog import filter_options, latest_email_subject, similar_band_ids
from app.clock import local_today
from app.models.act import Act
from app.models.band import Band
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.models.show import AgeRestriction, Show, ShowStatus
from app.models.venue import Region, Venue


def _venue(db, name="The Fillmore", region=Region.sf):
    v = Venue(name=name, city="San Francisco", region=region)
    db.add(v)
    db.flush()
    return v


def _show(db, venue, days_from_today=1, status=ShowStatus.upcoming, age=AgeRestriction.unknown, genres=None):
    s = Show(date=local_today() + timedelta(days=days_from_today), venue_id=venue.id, status=status,
             age_restriction=age)
    db.add(s)
    db.flush()
    b = Band(name=f"Band {s.id}", genres=genres or [])
    db.add(b)
    db.flush()
    db.add(Act(show_id=s.id, band_id=b.id, position=0))
    db.flush()
    return s


# ── filter_options ────────────────────────────────────────────────────────────

def test_filter_options_from_upcoming_shows_only(db):
    sf, oak = _venue(db), _venue(db, "Fox Theater", Region.east_bay)
    _show(db, sf, 1, age=AgeRestriction.plus_21, genres=["punk", "noise"])
    _show(db, oak, 2, age=AgeRestriction.all_ages, genres=["jazz"])
    _show(db, sf, 3, age=AgeRestriction.plus_18)
    _show(db, _venue(db, "Rio", Region.santa_cruz), -1, genres=["past-genre"])  # past
    _show(db, _venue(db, "Uptown", Region.north_bay), 4, status=ShowStatus.cancelled, genres=["gone"])

    opts = filter_options(db)

    today = local_today()
    assert opts.regions == ["east_bay", "sf"]
    assert opts.ages == ["a/a", "18+", "21+"]  # a/a first, then numeric; "unknown" left out
    assert opts.genres == ["jazz", "noise", "punk"]
    assert opts.dates == [str(today + timedelta(days=d)) for d in (1, 2, 3)]


def test_filter_options_includes_tonight(db):
    _show(db, _venue(db), 0)
    assert filter_options(db).dates == [str(local_today())]


def test_filter_options_empty(db):
    opts = filter_options(db)
    assert (opts.regions, opts.ages, opts.genres, opts.dates) == ([], [], [], [])


# ── similar_band_ids ──────────────────────────────────────────────────────────

def _band(db, name, embedding=True):
    b = Band(name=name, embedding=np.zeros(768, dtype=np.float32).tobytes() if embedding else None)
    db.add(b)
    db.flush()
    return b


def test_similar_band_ids_excludes_the_band_and_keeps_order(db):
    source, a, b = _band(db, "Source"), _band(db, "A", False), _band(db, "B", False)
    hits = [(source.id, 0.0), (b.id, 0.1), (a.id, 0.2)]
    with patch("app.catalog.find_similar_bands", return_value=hits) as search:
        assert similar_band_ids(db, source, k=2) == [b.id, a.id]
    assert search.call_args.args[1] == 3  # over-fetch by one


def test_similar_band_ids_truncates_to_k(db):
    source, a, b = _band(db, "Source"), _band(db, "A", False), _band(db, "B", False)
    with patch("app.catalog.find_similar_bands", return_value=[(a.id, 0.1), (b.id, 0.2)]):
        assert similar_band_ids(db, source, k=1) == [a.id]


def test_similar_band_ids_without_embedding_is_empty(db):
    band = _band(db, "No Embedding", embedding=False)
    with patch("app.catalog.find_similar_bands") as search:
        assert similar_band_ids(db, band, k=6) == []
        search.assert_not_called()


# ── latest_email_subject ──────────────────────────────────────────────────────

def _run(db, started_at, status, subject):
    db.add(IngestionRun(started_at=started_at, status=status, email_subject=subject))
    db.flush()


def test_latest_email_subject_uses_newest_successful_run(db):
    _run(db, datetime(2026, 9, 18, 9), IngestionStatus.success, "List for Friday, September 18th")
    _run(db, datetime(2026, 9, 25, 9), IngestionStatus.success, "List for Friday, September 25th")
    _run(db, datetime(2026, 10, 2, 9), IngestionStatus.failure, "List for Friday, October 2nd")
    assert latest_email_subject(db) == "List for Friday, September 25th"


def test_latest_email_subject_none_without_successful_runs(db):
    _run(db, datetime(2026, 10, 2, 9), IngestionStatus.no_email, None)
    assert latest_email_subject(db) is None
