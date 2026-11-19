"""Ingest jobs: Shows an admin asked for on the Admin page, one job per link or screenshot (ADR 0006). A link to a page
listing several events (an artist's page) adds each of them in the Bay Area: the job's Show is the first, and its
`shows_query` the Shows list's filter that picks them all out (`shows_query`).

The Admin page's Edge Function (supabase/functions/admin) puts each job in Supabase's `ingest_jobs` table and its
id on the `ingest_jobs` queue; the worker (supabase/functions/ingest-worker) hands queued jobs to the Ingest jobs
workflow (.github/workflows/ingest-jobs.yml), which runs `python -m app.cli ingest-jobs` against the data branch's
database. Each job's row says how far it has got (`status` and `phase`, with a `detail`), for the Admin page.

Finishing a job (`finish_job`) also deletes its queue message; a job the workflow never finishes (the run was
cancelled or crashed) comes back off the queue and is handed out again. A job that added Shows is finished only
once they're pushed to the data branch (`run_jobs` returns it as `Saved`; `finish_saved`, in a later step of the
workflow, finishes it): if the commit or push fails, the job is still on the queue and its Shows are added again.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from urllib.parse import urlencode
from datetime import date
from typing import Callable

import httpx
from sqlalchemy.orm import Session

from app.alerts import SupabaseError, _require_supabase
from app.config import settings
from app.ingestion.event_page import EventError, UnreadablePage, fetch_events
from app.ingestion.upsert import find_venue, venue_near
from app.models.show import Show

logger = logging.getLogger(__name__)

TABLE = "ingest_jobs"
BUCKET = "ingest-screenshots"
STATUSES = ("queued", "running", "review", "added", "live", "failed")
# What a failed link's message ends with when its page couldn't be read: the Admin page offers a screenshot then.
SCREENSHOT_INSTEAD = "Take a screenshot of the event and add that instead."
PHASES = ("queued", "dispatched", "fetching_page", "reading_screenshot", "review", "venue", "bands", "photos", "saving",
          "embedding", "committing", "deploying", "live")


@dataclass(frozen=True)
class Job:
    id: str
    msg_id: int
    provider: str  # "ticketweb" or "page" (a link, app/ingestion/event_page.py), or "screenshot"
    url: str | None
    screenshot_path: str | None
    status: str = "queued"
    # A screenshot job an admin has reviewed (approve_ingest_job): `extracted` is then the fields as they approved
    # them, ingested as they are; before review it's what the model read, if anything.
    extracted: dict | None = None
    approved: bool = False


@dataclass(frozen=True)
class Saved:
    """A job whose Shows are in the database but not yet pushed: how to finish it once they are (finish_saved)."""
    job_id: str
    msg_id: int
    message: str
    show_id: int
    extracted: dict | None = None
    shows_query: str | None = None


def save_outcomes(saved: list[Saved], path: str) -> None:
    with open(path, "w") as f:
        json.dump([asdict(s) for s in saved], f)


def load_outcomes(path: str) -> list[Saved]:
    with open(path) as f:
        return [Saved(**row) for row in json.load(f)]


def finish_saved(saved: list[Saved]) -> None:
    """Finish the jobs whose Shows are now pushed: "added", with what they did, and off the queue."""
    for s in saved:
        finish_job(Job(s.job_id, s.msg_id, "", None, None), "added", message=s.message, show_id=s.show_id,
                   extracted=s.extracted, shows_query=s.shows_query)


class NeedsReview(Exception):
    """A screenshot was read: an admin checks what was read (and corrects it) on the Admin page before it's added.
    `problem` is why it can't be added as it is, if it can't."""

    def __init__(self, fields: dict, problem: str | None = None):
        super().__init__(problem or "needs review")
        self.fields = fields
        self.problem = problem


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
        "select": "id,provider,url,screenshot_path,status,extracted,approved_at", "id": f"in.({ids})"}).json()
    by_id = {row["id"]: row for row in rows}
    return [Job(job_id, msg_id, row["provider"], row.get("url"), row.get("screenshot_path"),
                row.get("status", "queued"), row.get("extracted"), bool(row.get("approved_at")))
            for job_id, msg_id in pairs if (row := by_id.get(job_id))]


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
               extracted: dict | None = None, shows_query: str | None = None) -> None:
    """Record how the job's ingest came out and take it off the queue, together (finish_ingest_job, in
    supabase/migrations/0004_ingest_jobs.sql and 0008_ingest_jobs_shows_query.sql)."""
    body = {"job_id": job.id, "msg_id": job.msg_id, "new_status": status, "new_message": message,
            "new_show_id": show_id, "new_extracted": extracted}
    if shows_query:   # only a job that added several Shows has one
        body["new_shows_query"] = shows_query
    _request("POST", "/rest/v1/rpc/finish_ingest_job", json=body)


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


def known_venue_city(db: Session) -> Callable[..., str | None]:
    """For an event or screenshot that doesn't say where it is: the city of the List's Venue at its coordinates when
    it gives them, else of the Venue by its name. None when there's no such Venue, or it has no city."""
    def venue_city(name: str, coordinates: tuple[float, float] | None = None) -> str | None:
        venue = venue_near(db, *coordinates) if coordinates else find_venue(db, name)
        return venue.city if venue and venue.city not in (None, "", "Unknown") else None
    return venue_city


def read_job(db: Session, job: Job, today: date) -> tuple[list[dict], dict | None]:
    """The Shows a job asks for, as dicts for `ingest_shows` (one, unless its page lists several events), and for a
    screenshot what the model read."""
    venue_city = known_venue_city(db)
    if job.provider in ("ticketweb", "page"):
        update_jobs([job.id], phase="fetching_page", detail=job.url)
        return fetch_events(job.url or "", venue_city), None
    if job.provider == "screenshot":
        from app.ingestion.screenshot import ScreenshotError, read_fields, screenshot_show

        if job.approved:
            # As the admin approved it; if it still can't be added, it goes back to them with the reason.
            fields = job.extracted or {}
            update_jobs([job.id], phase="review", detail="Using the details as reviewed")
            try:
                return [screenshot_show(fields, today, venue_city)], fields
            except ScreenshotError as exc:
                raise NeedsReview(fields, str(exc)) from exc
        update_jobs([job.id], phase="reading_screenshot", detail=f"Reading it with {settings.vision_model}")
        fields = read_fields(download_screenshot(job.screenshot_path or ""))
        try:
            screenshot_show(fields, today, venue_city)
        except ScreenshotError as exc:
            raise NeedsReview(fields, str(exc)) from exc
        raise NeedsReview(fields)
    raise EventError(f"unknown provider {job.provider!r}")


def run_jobs(db: Session, jobs: list[Job], today: date, run_url: str | None = None) -> list[Saved]:
    """Ingest each job, recording on its row how far it gets and how it comes out. A job that fails doesn't stop the
    others; one an earlier run already finished (handed out twice, when a run outlasted its queue message's
    timeout) is skipped. A job that fails or goes to review is finished here; one that added (or updated) a Show
    stays running and on the queue, and is returned, to be finished once the data is pushed (finish_saved)."""
    added: list[Saved] = []
    for job in jobs:
        if job.status in ("added", "live"):
            logger.info("ingest-jobs: job %s was already %s", job.id, job.status)
            continue
        update_jobs([job.id], status="running", phase="dispatched", detail=None, message=None,
                    workflow_run_url=run_url)
        extracted = None
        try:
            shows, extracted = read_job(db, job, today)
            outcomes, failures = add_shows(db, job, shows)
        except SupabaseError:
            raise
        except NeedsReview as review:
            # Nothing is added from a screenshot until an admin has checked what was read.
            message = (f"Check what was read: {review.problem}" if review.problem
                       else "Check what was read, then approve it")
            print(f"ingest-jobs: job {job.id}: waiting for review ({review.problem or 'read'})")
            finish_job(job, "review", message=message, extracted=review.fields)
            continue
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
        message = outcome_message(job, outcomes, failures)
        print(f"ingest-jobs: job {job.id}: {message}")
        added.append(Saved(job.id, job.msg_id, message, outcomes[0][0].id, extracted,
                           shows_query([show for show, _ in outcomes])))
    return added


def add_shows(db: Session, job: Job, shows: list[dict]) -> tuple[list[tuple[Show, bool]], list[str]]:
    """Add a job's Shows: each Show and whether the List already had it, and what couldn't be added. A job's one Show
    that can't be added fails the job; of several, those that can are added, and the job fails only if none can."""
    def phases(which: str | None = None):
        def report(phase: str, detail: str | None) -> None:
            update_jobs([job.id], phase=phase, detail=f"{which}: {detail}" if which and detail else which or detail)
        return report

    if len(shows) == 1:
        return [add_show(db, shows[0], phases())], []
    outcomes, failures, first_error = [], [], None
    for number, data in enumerate(shows, 1):
        try:
            outcomes.append(add_show(db, data, phases(f"Show {number} of {len(shows)}")))
        except SupabaseError:
            raise
        except Exception as exc:
            db.rollback()
            logger.warning("ingest-jobs: job %s: couldn't add %s: %s", job.id, data.get("raw_text"), exc)
            failures.append(f"{data.get('raw_text')} ({exc})")
            first_error = first_error or exc
    if not outcomes:
        raise first_error
    return outcomes, failures


def shows_query(shows: list[Show]) -> str | None:
    """The Shows list's filter (frontend/src/lib/filters.ts) that picks out these Shows, for the Admin page's link to
    them: the Band they all have (the first one's headliner first), else the Venue they all share, from the first's date
    to the last's. None for one Show (its own page is the link), or Shows with neither in common."""
    if len(shows) < 2:
        return None
    first = [act.band_id for act in sorted(shows[0].acts, key=lambda act: act.position)]
    shared = set(first).intersection(*({act.band_id for act in show.acts} for show in shows[1:]))
    if shared:
        pin = ("bandId", next(band_id for band_id in first if band_id in shared))
    elif len({show.venue_id for show in shows}) == 1:
        pin = ("venueId", shows[0].venue_id)
    else:
        return None
    dates = [show.date for show in shows]
    return urlencode([pin, ("fromDate", min(dates).isoformat()), ("toDate", max(dates).isoformat())])


def outcome_message(job: Job, outcomes: list[tuple[Show, bool]], failures: list[str]) -> str:
    """What the job did, for its row on the Admin page."""
    if len(outcomes) == 1 and not failures:
        show, listed = outcomes[0]
        if listed:
            return f"The List already has it ({describe(show)})" + (
                "; added its ticket link" if job.provider != "screenshot" else "; nothing added")
        return f"Added {describe(show)}"
    each = [describe(show) + (" (the List already had it; added its ticket link)" if listed else "")
            for show, listed in outcomes]
    message = f"Added {len(outcomes)} Show{'' if len(outcomes) == 1 else 's'}: " + "; ".join(each)
    if failures:
        message += f". Couldn't add {len(failures)}: " + "; ".join(failures)
    return message
