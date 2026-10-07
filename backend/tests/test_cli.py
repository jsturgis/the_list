"""Tests for the `ingest` command the weekly GitHub Action runs."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.cli import main


@patch("app.cli._run_ingestion_async", new_callable=AsyncMock)
@patch("app.cli.run_daily_maintenance")
def test_ingest_runs_maintenance_then_ingestion(maintenance, ingestion):
    calls = []
    maintenance.side_effect = lambda: calls.append("maintenance")
    ingestion.side_effect = lambda: calls.append("ingestion")
    main(["ingest"])  # returns normally: exit status 0
    assert calls == ["maintenance", "ingestion"]


@patch("app.cli._run_ingestion_async", new_callable=AsyncMock, side_effect=RuntimeError("Drive unreachable"))
@patch("app.cli.run_daily_maintenance")
def test_ingest_exits_non_zero_when_the_run_fails(maintenance, ingestion):
    with pytest.raises(SystemExit) as exit_:
        main(["ingest"])
    assert exit_.value.code == 1


@patch("app.cli._run_ingestion_async", new_callable=AsyncMock)
@patch("app.cli.run_daily_maintenance", side_effect=RuntimeError("database is locked"))
def test_ingest_exits_non_zero_when_maintenance_fails(maintenance, ingestion):
    with pytest.raises(SystemExit) as exit_:
        main(["ingest"])
    assert exit_.value.code == 1
    ingestion.assert_not_called()


def _key_checks(lastfm=None, discogs=None, model=None):
    """The Last.fm, Discogs and genre model checks, answering with these problems (None: it works)."""
    return patch.multiple("app.ingestion.lastfm", lastfm_key_problem=lambda: lastfm), \
        patch.multiple("app.ingestion.discogs", discogs_key_problem=lambda: discogs), \
        patch.multiple("app.ingestion.genre_filter", genre_model_problem=lambda: model)


def test_backfill_runs_with_the_time_budget_and_limit(capsys):
    result = {"looked_up": 3, "failed": 1, "remaining": 40}
    lastfm, discogs, model = _key_checks()
    with patch("app.ingestion.backfill.run_backfill", new=AsyncMock(return_value=result)) as run, \
         patch("app.cli.SessionLocal"), lastfm, discogs, model:
        main(["backfill", "--max-minutes", "5", "--limit", "4"])
    assert run.await_args.kwargs == {"max_minutes": 5.0, "limit": 4}
    assert "looked up 3 bands (1 failed); 40 still to do" in capsys.readouterr().out


def test_backfill_wont_run_when_a_service_rejects_its_key():
    lastfm, discogs, model = _key_checks(lastfm="Last.fm rejected LASTFM_API_KEY (error 10: Invalid API key)")
    with patch("app.ingestion.backfill.run_backfill", new=AsyncMock()) as run, lastfm, discogs, model, \
         pytest.raises(SystemExit, match="error 10: Invalid API key"):
        main(["backfill"])
    run.assert_not_called()


def test_backfill_wont_run_without_the_genre_model():
    lastfm, discogs, model = _key_checks(model="couldn't ask the genre model tev1:0.8b")
    with patch("app.ingestion.backfill.run_backfill", new=AsyncMock()) as run, lastfm, discogs, model, \
         pytest.raises(SystemExit, match="genre model"):
        main(["backfill"])
    run.assert_not_called()


def test_backfill_can_first_recheck_genres(capsys):
    lastfm, discogs, model = _key_checks()
    result = {"looked_up": 2, "failed": 0, "remaining": 0}
    with patch("app.ingestion.backfill.recheck_genres", return_value=2) as recheck, \
         patch("app.ingestion.backfill.run_backfill", new=AsyncMock(return_value=result)), \
         patch("app.cli.SessionLocal"), lastfm, discogs, model:
        main(["backfill", "--recheck-genres"])
    recheck.assert_called_once()
    assert "2 bands with tags that aren't genres" in capsys.readouterr().out


def test_photo_focus_fills_in_missing_focal_points(capsys):
    counts = {"bands": 12, "with_faces": 9, "faces": 15, "skipped": 1}
    with patch("app.ingestion.band_photos.fill_photo_focus", return_value=counts) as fill, patch("app.cli.SessionLocal"):
        main(["photo-focus"])
    assert fill.call_args.kwargs == {"recompute": False}
    assert "12 bands (9 photos with faces, 15 faces); 1 skipped" in capsys.readouterr().out


def test_photo_focus_all_recomputes_every_stored_photo():
    with patch("app.ingestion.band_photos.fill_photo_focus", return_value={"bands": 0, "with_faces": 0, "faces": 0,
                                                                           "skipped": 0}) as fill, \
         patch("app.cli.SessionLocal"):
        main(["photo-focus", "--all"])
    assert fill.call_args.kwargs == {"recompute": True}
