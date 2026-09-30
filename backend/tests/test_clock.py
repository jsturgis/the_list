"""Tests for local-date helpers."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.clock import local_today


def test_local_today_uses_bay_area_date_when_utc_is_already_tomorrow():
    # 6:15pm PDT on Sep 29 is 01:15 UTC on Sep 30.
    now = datetime(2026, 9, 30, 1, 15, tzinfo=timezone.utc)
    assert local_today(now) == date(2026, 9, 29)


def test_local_today_matches_utc_date_in_the_morning():
    now = datetime(2026, 9, 29, 16, 0, tzinfo=timezone.utc)  # 9am PDT
    assert local_today(now) == date(2026, 9, 29)
