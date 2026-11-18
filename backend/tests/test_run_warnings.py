"""The warnings an ingest logs, kept on its run (app/run_warnings.py)."""
from __future__ import annotations

import logging
import threading

from app.config import settings
from app.run_warnings import MAX_WARNINGS, WarningCollector


def _collecting():
    collector = WarningCollector()
    logging.getLogger("app").addHandler(collector)
    return collector


def test_warnings_are_counted_by_message_in_the_order_first_logged():
    collector = _collecting()
    try:
        log = logging.getLogger("app.scheduler")
        log.info("not a warning")
        log.warning("venue calendars skipped this run")
        log.warning("%s didn't answer: %s", "Discogs", "ConnectError")
        log.warning("%s didn't answer: %s", "Discogs", "ConnectError")
        threading.Thread(target=lambda: log.error("from a worker thread")).start()
        logging.getLogger("elsewhere").warning("not the app's")
    finally:
        logging.getLogger("app").removeHandler(collector)

    assert collector.warnings() == [
        {"message": "venue calendars skipped this run", "count": 1},
        {"message": "Discogs didn't answer: ConnectError", "count": 2},
        {"message": "from a worker thread", "count": 1},
    ]


def test_credentials_are_taken_out_and_there_are_at_most_so_many(monkeypatch):
    monkeypatch.setattr(settings, "lastfm_api_key", "lastfm-secret-123")
    collector = _collecting()
    try:
        log = logging.getLogger("app.ingestion.lastfm")
        log.warning("Last.fm didn't answer: https://ws.audioscrobbler.com/2.0/?api_key=lastfm-secret-123&x=1")
        for i in range(MAX_WARNINGS + 5):
            log.warning("warning %d", i)
    finally:
        logging.getLogger("app").removeHandler(collector)

    warnings = collector.warnings()
    assert len(warnings) == MAX_WARNINGS
    assert "lastfm-secret-123" not in warnings[0]["message"]
