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


def _key_checks(lastfm=None, discogs=None):
    """The Last.fm and Discogs key checks, answering with these problems (None: the key works)."""
    return patch.multiple("app.ingestion.lastfm", lastfm_key_problem=lambda: lastfm), \
        patch.multiple("app.ingestion.discogs", discogs_key_problem=lambda: discogs)


def test_backfill_runs_with_the_time_budget_and_limit(capsys):
    result = {"looked_up": 3, "failed": 1, "remaining": 40}
    lastfm, discogs = _key_checks()
    with patch("app.ingestion.backfill.run_backfill", new=AsyncMock(return_value=result)) as run, \
         patch("app.cli.SessionLocal"), lastfm, discogs:
        main(["backfill", "--max-minutes", "5", "--limit", "4"])
    assert run.await_args.kwargs == {"max_minutes": 5.0, "limit": 4}
    assert "looked up 3 bands (1 failed); 40 still to do" in capsys.readouterr().out


def test_backfill_wont_run_when_a_service_rejects_its_key():
    lastfm, discogs = _key_checks(lastfm="Last.fm rejected LASTFM_API_KEY (error 10: Invalid API key)")
    with patch("app.ingestion.backfill.run_backfill", new=AsyncMock()) as run, lastfm, discogs, \
         pytest.raises(SystemExit, match="error 10: Invalid API key"):
        main(["backfill"])
    run.assert_not_called()
