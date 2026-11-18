"""The warnings an ingest logs, kept on its ingestion run (IngestionRun.warnings) and put in the maintainer's email.

An ingest carries on past what it can't do (a Venue Google can't confirm, a service that's down, the venue
calendars or the embeddings skipped, too many Shows gone from the page to remove any), saying so only in the log.
A WarningCollector on the "app" logger (app/scheduler.py) catches every warning the app's loggers log meanwhile,
from any thread, so each of those shows up
without its own plumbing. Credentials are taken out (they can be in a failed request's URL), as the data branch,
and so the database, is public.
"""
from __future__ import annotations

import logging
import threading

# The most warnings kept on a run, and of each message: what makes it to the email.
MAX_WARNINGS = 30
MAX_MESSAGE_CHARS = 300


class WarningCollector(logging.Handler):
    """Each distinct warning message logged, with how many times."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self._lock_counts = threading.Lock()
        self.counts: dict[str, int] = {}

    def emit(self, record: logging.LogRecord) -> None:
        try:
            lines = record.getMessage().strip().splitlines() or [""]
        except Exception:  # a bad format string mustn't break the ingest
            return
        message = lines[0][:MAX_MESSAGE_CHARS]
        with self._lock_counts:
            self.counts[message] = self.counts.get(message, 0) + 1

    def warnings(self) -> list[dict]:
        """[{"message", "count"}], in the order first logged, credentials taken out, at most MAX_WARNINGS."""
        from app.notifications import _secrets, redact

        secrets = _secrets()
        with self._lock_counts:
            items = list(self.counts.items())
        return [{"message": redact(message, secrets), "count": count} for message, count in items[:MAX_WARNINGS]]

