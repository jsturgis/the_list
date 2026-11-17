"""Ingest jobs: Shows an admin asked for on the Admin page, one per TicketWeb link or screenshot (ADR 0006).

The Admin page's Edge Function (supabase/functions/admin) puts each job in Supabase's `ingest_jobs` table and its
id on the `ingest_jobs` queue; the worker (supabase/functions/ingest-worker) hands queued jobs to the Ingest jobs
workflow (.github/workflows/ingest-jobs.yml), which runs `python -m app.cli ingest-jobs` against the data branch's
database. Each job's row says how far it has got (`status` and `phase`, with a `detail`), for the Admin page.

Finishing a job (`finish_job`) also deletes its queue message; a job the workflow never finishes (the run was
cancelled or crashed) comes back off the queue and is handed out again.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable

import httpx
from sqlalchemy.orm import Session

from app.alerts import SupabaseError, _require_supabase
from app.config import settings
from app.ingestion.event_page import EventError, UnreadablePage, fetch_event
from app.ingestion.upsert import find_venue
from app.models.show import Show

logger = logging.getLogger(__name__)

TABLE = "ingest_jobs"
BUCKET = "ingest-screenshots"
STATUSES = ("queued", "running", "added", "live", "failed")
# What a failed link's message ends with when its page couldn't be read: the Admin page offers a screenshot then.
SCREENSHOT_INSTEAD = "Take a screenshot of the event and add that instead."
PHASES = ("queued", "dispatched", "fetching_page", "reading_screenshot", "venue", "bands", "photos", "saving",
          "embedding", "committing", "deploying", "live")


@dataclass(frozen=True)
class Job:
    id: str
    msg_id: int
    provider: str  # "ticketweb" or "page" (a link, app/ingestion/event_page.py), or "screenshot"
    url: str | None
    screenshot_path: str | None
    status: str = "queued"


def parse_specs(specs: str) -> list[tuple[str, int]]:
    """The workflow's `jobs` input, "job_id:msg_id,..." (the worker's), as (job id, queue message id) pairs."""
    pairs = []
    for spec in filter(None, (s.strip() for s in specs.split(","))):
        job_id, _, msg_id = spec.partition(":")
        if not job_id or not msg_id.isdigit():
            raise ValueError(f"bad job {spec!r}: expected job_id:msg_id")
        pairs.append((job_id, int(msg_id)))
    return pairs


# ── Supabase ──────────────────────────────────────────────────────────────────

def _request(method: str, path: str, **kwargs) -> httpx.Response:
    # The secret key (sb_secret_...) goes in `apikey`; it isn't a JWT, so no Authorization header (see app/alerts.py).
    _require_supabase()
    headers = {"apikey": settings.supabase_service_role_key, **kwargs.pop("headers", {})}
    try:
        response = httpx.request(method, f"{settings.supabase_url.rstrip('/')}{path}", headers=headers, timeout=60.0,
                                 **kwargs)
        response.raise_for_status()
        return response
    except Exception as exc:
        raise SupabaseError(f"Supabase {method} {path} failed: {exc}") from exc


def fetch_jobs(pairs: list[tuple[str, int]]) -> list[Job]:
    """The jobs these are, in the order given; those no longer in the table are left out."""
    if not pairs:
        return []
    ids = ",".join(job_id for job_id, _ in pairs)
    rows = _request("GET", f"/rest/v1/{TABLE}", params={
        "select": "id,provider,url,screenshot_path,status", "id": f"in.({ids})"}).json()
    by_id = {row["id"]: row for row in rows}
    return [Job(job_id, msg_id, by_id[job_id]["provider"], by_id[job_id].get("url"),
                by_id[job_id].get("screenshot_path"), by_id[job_id].get("status", "queued"))
            for job_id, msg_id in pairs if job_id in by_id]


def update_jobs(job_ids: list[str], **fields) -> None:
    """Set these fields on these jobs' rows (status, phase, detail, message, workflow_run_url...)."""
    if not job_ids:
        return
    _request("PATCH", f"/rest/v1/{TABLE}", params={"id": f"in.({','.join(job_ids)})"}, json=fields,
             headers={"Prefer": "return=minimal"})


def unfinished(job_ids: list[str]) -> list[str]:
    """Those of these jobs that haven't finished ingesting (still queued or running)."""
    if not job_ids:
        return []
    rows = _request("GET", f"/rest/v1/{TABLE}", params={
        "select": "id", "id": f"in.({','.join(job_ids)})", "status": "in.(queued,running)"}).json()
    return [row["id"] for row in rows]


def finish_job(job: Job, status: str, *, message: str | None = None, show_id: int | None = None,
               extracted: dict | None = None) -> None:
    """Record how the job's ingest came out and take it off the queue, together (finish_ingest_job, in
    supabase/migrations/0004_ingest_jobs.sql)."""
    _request("POST", "/rest/v1/rpc/finish_ingest_job", json={
        "job_id": job.id, "msg_id": job.msg_id, "new_status": status, "new_message": message,
        "new_show_id": show_id, "new_extracted": extracted})


def download_screenshot(path: str) -> bytes:
    return _request("GET", f"/storage/v1/object/{BUCKET}/{path}").content


# ── Ingesting ─────────────────────────────────────────────────────────────────

def add_show(db: Session, data: dict, on_phase: Callable[[str, str | None], None] | None = None) -> tuple[Show, bool]:
    """Ingest one Show added by hand (an event page, a screenshot), looking its new Venue and Bands up as the ingest
    does. Returns the Show and whether the List already had it, in which case only its ticket link was added: the
    List wins."""
    from app.scheduler import ingest_shows

    (show,) = asyncio.run(ingest_shows(db, [data], on_phase=on_phase))
    return show, show.source != data["source"]


def describe(show: Show) -> str:
    lineup = ", ".join(act.band.name for act in sorted(show.acts, key=lambda a: a.position))
    return f"{lineup} at {show.venue.name}, {show.venue.city} on {show.date:%a %b %-d, %Y}"


def read_job(db: Session, job: Job, today: date) -> tuple[dict, dict | None]:
    """The Show a job asks for, as a dict for `ingest_shows`, and for a screenshot what the model read."""
    if job.provider in ("ticketweb", "page"):
        update_jobs([job.id], phase="fetching_page", detail=job.url)
        return fetch_event(job.url or ""), None
    if job.provider == "screenshot":
        from app.ingestion.screenshot import read_screenshot

        update_jobs([job.id], phase="reading_screenshot", detail=f"Reading it with {settings.vision_model}")
        image = download_screenshot(job.screenshot_path or "")

        def venue_city(name: str) -> str | None:
            venue = find_venue(db, name)
            return venue.city if venue else None

        data = read_screenshot(image, today, venue_city)
        return data, data.pop("fields")
    raise EventError(f"unknown provider {job.provider!r}")


def run_jobs(db: Session, jobs: list[Job], today: date, run_url: str | None = None) -> list[str]:
    """Ingest each job, recording on its row how far it gets and how it comes out. A job that fails doesn't stop the
    others; one an earlier run already finished (handed out twice, when a run outlasted its queue message's
    timeout) is skipped. Returns the ids of the jobs that added (or updated) a Show."""
    added = []
    for job in jobs:
        if job.status in ("added", "live"):
            logger.info("ingest-jobs: job %s was already %s", job.id, job.status)
            continue
        update_jobs([job.id], status="running", phase="dispatched", detail=None, message=None,
                    workflow_run_url=run_url)
        extracted = None
        try:
            data, extracted = read_job(db, job, today)
            show, listed = add_show(db, data, lambda phase, detail: update_jobs([job.id], phase=phase, detail=detail))
        except SupabaseError:
            raise
        except EventError as exc:
            logger.warning("ingest-jobs: job %s: %s", job.id, exc)
            message = f"{exc}. {SCREENSHOT_INSTEAD}" if isinstance(exc, UnreadablePage) else str(exc)
            finish_job(job, "failed", message=message, extracted=getattr(exc, "fields", None) or extracted)
            continue
        except Exception as exc:
            db.rollback()
            logger.exception("ingest-jobs: job %s failed", job.id)
            finish_job(job, "failed", message=f"{type(exc).__name__}: {exc}", extracted=extracted)
            continue
        if listed:
            message = f"The List already has it ({describe(show)})" + (
                "; added its ticket link" if job.provider != "screenshot" else "; nothing added")
        else:
            message = f"Added {describe(show)}"
        print(f"ingest-jobs: job {job.id}: {message}")
        finish_job(job, "added", message=message, show_id=show.id, extracted=extracted)
        added.append(job.id)
    return added
