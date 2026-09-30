"""Tests for the ingestionRuns GraphQL query."""
from __future__ import annotations

from datetime import datetime

from app.models.ingestion_run import IngestionRun, IngestionStatus


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(db, started_at, status=IngestionStatus.success, **kwargs):
    r = IngestionRun(started_at=started_at, status=status, **kwargs)
    db.add(r)
    db.flush()
    return r


def _gql(client, query):
    resp = client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    return resp.json()


# ── ingestionRuns ─────────────────────────────────────────────────────────────

def test_ingestion_runs_returns_fields(db, client):
    _run(
        db,
        datetime(2026, 9, 25, 9, 0),
        finished_at=datetime(2026, 9, 25, 9, 5),
        email_subject="San Francisco Area Music List for Friday, September 25th, 2026",
        shows_parsed=1205,
        shows_upserted=1205,
        shows_new=40,
    )

    body = _gql(client, """{ ingestionRuns {
        startedAt finishedAt status emailSubject showsParsed showsUpserted showsNew error
    } }""")

    assert "errors" not in body
    run = body["data"]["ingestionRuns"][0]
    assert run["startedAt"] == "2026-09-25T09:00:00"
    assert run["finishedAt"] == "2026-09-25T09:05:00"
    assert run["status"] == "success"
    assert run["emailSubject"].startswith("San Francisco Area Music List")
    assert (run["showsParsed"], run["showsUpserted"], run["showsNew"]) == (1205, 1205, 40)
    assert run["error"] is None


def test_ingestion_runs_newest_first_and_limited(db, client):
    for day in (18, 25, 11):
        _run(db, datetime(2026, 9, day, 9, 0))

    body = _gql(client, "{ ingestionRuns(limit: 2) { startedAt } }")

    assert [r["startedAt"][:10] for r in body["data"]["ingestionRuns"]] == ["2026-09-25", "2026-09-18"]


def test_ingestion_runs_filter_by_status(db, client):
    _run(db, datetime(2026, 9, 18, 9, 0), status=IngestionStatus.failure, error="IMAP timeout")
    _run(db, datetime(2026, 9, 25, 9, 0), status=IngestionStatus.success)

    body = _gql(client, '{ ingestionRuns(status: "failure") { status error } }')

    assert body["data"]["ingestionRuns"] == [{"status": "failure", "error": "IMAP timeout"}]


def test_ingestion_runs_invalid_status_returns_error(client):
    body = _gql(client, '{ ingestionRuns(status: "bogus") { id } }')
    assert "errors" in body
