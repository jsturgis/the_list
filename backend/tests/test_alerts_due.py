"""Whether the newest edition is still due its Alerts (app/scheduler.py alerts_due), for the hourly check."""
from __future__ import annotations

from datetime import date, datetime

from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.scheduler import alerts_due, mark_alerts_sent

_FRIDAY = date(2026, 11, 13)


def _run(db, edition, status=IngestionStatus.success, sent=None):
    run = IngestionRun(started_at=datetime(2026, 11, 13), status=status, edition_date=edition, alerts_sent_at=sent)
    db.add(run)
    db.commit()
    return run


def test_nothing_ingested_is_never_due(db):
    assert not alerts_due(db, today=_FRIDAY)


def test_an_edition_whose_alerts_didnt_go_out_is_due_until_its_week_ends(db):
    _run(db, _FRIDAY)
    assert alerts_due(db, today=_FRIDAY)
    assert alerts_due(db, today=date(2026, 11, 19))       # its Thursday
    assert not alerts_due(db, today=date(2026, 11, 20))   # the next edition's week


def test_a_correction_in_the_same_week_counts_as_the_same_edition(db):
    _run(db, _FRIDAY, sent=datetime(2026, 11, 13, 9))
    _run(db, date(2026, 11, 16))   # Monday's correction, ingested since
    assert not alerts_due(db, today=date(2026, 11, 16))


def test_a_failed_run_isnt_an_edition(db):
    _run(db, date(2026, 11, 6), sent=datetime(2026, 11, 6, 9))
    _run(db, _FRIDAY, status=IngestionStatus.failure)
    assert not alerts_due(db, today=_FRIDAY)


def test_marking_records_on_the_newest_run_of_the_newest_edition(db):
    _run(db, date(2026, 11, 6), sent=datetime(2026, 11, 6, 9))
    _run(db, _FRIDAY)
    newest = _run(db, date(2026, 11, 14))
    assert alerts_due(db, today=date(2026, 11, 14))

    assert mark_alerts_sent(db) is newest
    assert newest.alerts_sent_at is not None
    assert not alerts_due(db, today=date(2026, 11, 14))


def test_marking_with_nothing_ingested_records_nothing(db):
    assert mark_alerts_sent(db) is None
