"""Tests for the ingestionRuns GraphQL query."""
from __future__ import annotations

from datetime import date, datetime

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
        edition_title="The List for Sep 25, 2026",
        edition_date=date(2026, 9, 25),
        source_hash="5471f789b974",
        shows_parsed=1205,
        shows_upserted=1205,
        shows_new=40,
        new_venues=3,
    )

    body = _gql(client, """{ ingestionRuns {
        startedAt finishedAt status editionTitle editionDate sourceHash showsParsed showsUpserted showsNew newVenues error
    } }""")

    assert "errors" not in body
    run = body["data"]["ingestionRuns"][0]
    assert run["startedAt"] == "2026-09-25T09:00:00"
    assert run["finishedAt"] == "2026-09-25T09:05:00"
    assert run["status"] == "success"
    assert (run["editionTitle"], run["editionDate"], run["sourceHash"]) == (
        "The List for Sep 25, 2026", "2026-09-25", "5471f789b974")
    assert (run["showsParsed"], run["showsUpserted"], run["showsNew"]) == (1205, 1205, 40)
    assert run["newVenues"] == 3
    assert run["error"] is None


def test_ingestion_runs_newest_first_and_limited(db, client):
    for day in (18, 25, 11):
        _run(db, datetime(2026, 9, day, 9, 0))

    body = _gql(client, "{ ingestionRuns(limit: 2) { startedAt } }")

    assert [r["startedAt"][:10] for r in body["data"]["ingestionRuns"]] == ["2026-09-25", "2026-09-18"]


def test_ingestion_runs_filter_by_status(db, client):
    _run(db, datetime(2026, 9, 18, 9, 0), status=IngestionStatus.failure, error="stevelist.com timed out")
    _run(db, datetime(2026, 9, 25, 9, 0), status=IngestionStatus.success)

    body = _gql(client, '{ ingestionRuns(status: "failure") { status error } }')

    assert body["data"]["ingestionRuns"] == [{"status": "failure", "error": "stevelist.com timed out"}]


def test_ingestion_runs_invalid_status_returns_error(client):
    body = _gql(client, '{ ingestionRuns(status: "bogus") { id } }')
    assert "errors" in body


# ── the migration to runs of the List page ────────────────────────────────────

def test_the_migration_turns_email_runs_into_edition_runs(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    def alembic(*args):
        subprocess.run([sys.executable, "-m", "alembic", *args], cwd=Path(__file__).parent.parent, check=True,
                       env={**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}, capture_output=True)

    # The table as it was: runs of the formatted edition from Drive.
    db_path = tmp_path / "migrated.db"
    with sqlite3.connect(db_path) as con:
        con.execute("""CREATE TABLE ingestion_runs (id INTEGER PRIMARY KEY, started_at DATETIME NOT NULL,
            finished_at DATETIME, status VARCHAR(8) NOT NULL, email_received_at DATETIME, email_subject VARCHAR(500),
            email_message_id VARCHAR(200), shows_parsed INTEGER, shows_upserted INTEGER, shows_new INTEGER, error TEXT,
            new_bands INTEGER, new_bands_without_photo_pct FLOAT, new_bands_photo_from_edition_pct FLOAT,
            new_bands_genres_from_edition_pct FLOAT, new_bands_links_from_edition_pct FLOAT)""")
        con.execute("""INSERT INTO ingestion_runs (id, started_at, status, email_received_at, email_subject,
            email_message_id, shows_parsed, new_bands, new_bands_without_photo_pct) VALUES
            (1, '2026-11-07 02:10:00', 'success', '2026-11-06 00:00:00.000000', 'Concert Events — Nov 6, 2026',
             'drive-file-id', 1011, 40, 12.5),
            (2, '2026-11-14 06:40:00', 'no_email', NULL, NULL, NULL, 0, NULL, NULL)""")
    alembic("stamp", "e6f8a0b2c4d7")

    alembic("upgrade", "b7d1f3a5c9e2")
    with sqlite3.connect(db_path) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(ingestion_runs)")}
        assert {"edition_date", "edition_title", "source_hash"} <= columns
        assert not {c for c in columns if c.startswith("email_") or c.endswith("_from_edition_pct")}
        # The run that found no edition is gone with its status; a Drive file id isn't a page hash.
        assert con.execute("""SELECT id, status, edition_date, edition_title, source_hash, shows_parsed, new_bands,
            new_bands_without_photo_pct FROM ingestion_runs""").fetchall() == [
            (1, "success", "2026-11-06", "Concert Events — Nov 6, 2026", None, 1011, 40, 12.5)]

    alembic("downgrade", "e6f8a0b2c4d7")
    with sqlite3.connect(db_path) as con:
        assert con.execute("SELECT email_received_at, email_subject FROM ingestion_runs").fetchall() == [
            ("2026-11-06 00:00:00.000000", "Concert Events — Nov 6, 2026")]


def test_the_migration_adds_the_new_venues_count(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    def alembic(*args):
        subprocess.run([sys.executable, "-m", "alembic", *args], cwd=Path(__file__).parent.parent, check=True,
                       env={**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}, capture_output=True)

    db_path = tmp_path / "migrated.db"
    with sqlite3.connect(db_path) as con:
        con.execute("""CREATE TABLE ingestion_runs (id INTEGER PRIMARY KEY, started_at DATETIME NOT NULL,
            finished_at DATETIME, status VARCHAR(7) NOT NULL, edition_date DATE, edition_title VARCHAR(500),
            source_hash VARCHAR(64), shows_parsed INTEGER, shows_upserted INTEGER, shows_new INTEGER, error TEXT,
            new_bands INTEGER, new_bands_without_photo_pct FLOAT)""")
        con.execute("""INSERT INTO ingestion_runs (id, started_at, status, edition_title, shows_new, new_bands)
            VALUES (1, '2026-11-13 09:00:00', 'success', 'The List for Nov 13, 2026', 40, 12)""")
    alembic("stamp", "b7d1f3a5c9e2")

    alembic("upgrade", "c8e2a4b6d0f3")
    with sqlite3.connect(db_path) as con:
        # Runs from before the count have none.
        assert con.execute("SELECT id, shows_new, new_bands, new_venues FROM ingestion_runs").fetchall() == [
            (1, 40, 12, None)]

    alembic("downgrade", "b7d1f3a5c9e2")
    with sqlite3.connect(db_path) as con:
        assert "new_venues" not in {row[1] for row in con.execute("PRAGMA table_info(ingestion_runs)")}
        assert con.execute("SELECT id, new_bands FROM ingestion_runs").fetchall() == [(1, 12)]
