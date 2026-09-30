"""Tests for when the scheduled jobs run (Bay Area time, not the server's UTC)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.scheduler import scheduler


def _next_utc(job_id: str, after_utc: datetime) -> datetime:
    return scheduler.get_job(job_id).trigger.get_next_fire_time(None, after_utc).astimezone(timezone.utc)


def test_weekly_ingestion_runs_friday_8pm_pacific():
    # Fri Oct 2 2026, noon UTC (5am PDT) -> Fri 8pm PDT = Sat 03:00 UTC
    assert _next_utc("weekly_ingestion", datetime(2026, 10, 2, 12, tzinfo=timezone.utc)) == \
        datetime(2026, 10, 3, 3, tzinfo=timezone.utc)


def test_weekly_ingestion_follows_daylight_saving():
    # After DST ends (Nov 1 2026): Fri Nov 6 8pm PST = Sat 04:00 UTC
    assert _next_utc("weekly_ingestion", datetime(2026, 11, 6, 12, tzinfo=timezone.utc)) == \
        datetime(2026, 11, 7, 4, tzinfo=timezone.utc)


def test_daily_maintenance_runs_at_midnight_pacific():
    # Midnight PDT = 07:00 UTC
    assert _next_utc("daily_maintenance", datetime(2026, 10, 2, 12, tzinfo=timezone.utc)) == \
        datetime(2026, 10, 3, 7, tzinfo=timezone.utc)
