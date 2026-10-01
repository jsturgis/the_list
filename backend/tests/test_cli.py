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
