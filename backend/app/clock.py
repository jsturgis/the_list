"""Local-time helpers. Shows are listed by Bay Area calendar date, not the server's (UTC) date."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import settings


def local_today(now: datetime | None = None) -> date:
    """Today's date in settings.timezone. `now` (timezone-aware) is for tests."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo(settings.timezone)).date()
