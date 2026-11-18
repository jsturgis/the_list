"""The maintainer's emails about the ingest (not Alerts: those go to people with Saved Filters, app/alerts.py).

Two emails, both to settings.maintainer_email through Resend, sent by steps of the Deploy workflow:

- after each successful ingest that brought new Shows or logged warnings (`python -m app.cli notify-success`): the
  edition, its Show counts, how many new Bands and new Venues it brought, and what it carried on past (its
  warnings, app/run_warnings.py);
- while the ingest is failing (`python -m app.cli notify-failure --stage check|ingest --log PATH`): the root cause
  and the end of the failing command's log. Only once the last successful ingest is FAILING_AFTER_DAYS old, and at
  most once a day.

A failed ingestion run isn't committed to the data branch, and a failed check records no run, so nothing in the
database counts failures. "Failing for two weeks" is therefore: this attempt failed, and the newest successful run
finished two weeks ago or more. A List that hasn't changed for two weeks isn't a failure (its checks succeed), so
only a failed attempt gets here. A database with no successful run sends nothing.

Without MAINTAINER_EMAIL or RESEND_API_KEY both commands log that they're skipping and send nothing.
"""
from __future__ import annotations

import hashlib
import html
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping, TextIO

import httpx
from sqlalchemy.orm import Session

from app.clock import local_today
from app.config import settings
from app.mailer import SendError, post_email
from app.models.ingestion_run import IngestionRun, IngestionStatus

logger = logging.getLogger(__name__)

# The failure email starts once the last successful ingest is this old.
FAILING_AFTER_DAYS = 14
# How much of the failing command's log the failure email carries: its last lines, and no more than this many characters.
LOG_TAIL_LINES = 60
LOG_TAIL_CHARS = 6000
# Only the end of a log file is read.
_LOG_READ_BYTES = 200_000
_CAUSE_CHARS = 500
_SUBJECT_CAUSE_CHARS = 120

STAGES = ("check", "ingest")

_TRACEBACK = "Traceback (most recent call last):"
_CHAINED = ("The above exception was the direct cause of the following exception:",
            "During handling of the above exception, another exception occurred:")
# A line of the CLI's log ("2026-11-13 09:00:01,123 ERROR app.cli: check failed: ..."): its message.
_ERROR_LINE = re.compile(r"^\S+ \S+ (?:ERROR|CRITICAL) [\w.]+: (?P<message>.+)$")
_LOG_PREFIXES = ("check failed: ", "ingest failed: ")

_REDACTED = "[redacted]"
# Credentials in a URL's query string or a header: api_key=, key=, access_token=, client_secret=, password=, ...
# The value ends at what follows a URL's query or a log message's next field ("...?api_key=abc: 503").
_CREDENTIAL_PARAM = re.compile(r"(?i)\b([\w-]*(?:key|token|secret|password|signature))=([^&\s\"'<>,;:)]+)")
_AUTH_SCHEME = re.compile(r"(?i)\b(bearer|basic)\s+[\w.~+/=-]+")
_AUTH_HEADER = re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)(?!bearer\b|basic\b)[^\s\"',}]+")


@dataclass
class Notification:
    subject: str
    text: str
    html: str


@dataclass
class LastSuccess:
    """The newest successful ingestion run: when it finished, and the edition it ingested."""

    finished_at: datetime
    edition_title: str | None
    edition_date: date | None


# ── the failing command's log ─────────────────────────────────────────────────

def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    """`text` without credentials: query-string and header ones (`api_key=`, `key=`, `token=`, `secret=`,
    Authorization and Bearer values), and each of `secrets` wherever it appears."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, _REDACTED)
    text = _CREDENTIAL_PARAM.sub(rf"\1={_REDACTED}", text)
    text = _AUTH_SCHEME.sub(rf"\1 {_REDACTED}", text)
    return _AUTH_HEADER.sub(rf"\g<1>{_REDACTED}", text)


def _secrets() -> tuple[str, ...]:
    """Every key in the settings, so one that got into a log some other way is still taken out."""
    values = (settings.resend_api_key, settings.google_maps_api_key, settings.lastfm_api_key,
              settings.discogs_consumer_key, settings.discogs_consumer_secret, settings.supabase_service_role_key,
              settings.anthropic_api_key)
    return tuple(v for v in values if v and len(v) >= 8)


def tail(text: str, lines: int = LOG_TAIL_LINES, chars: int = LOG_TAIL_CHARS) -> str:
    """The last `lines` lines of `text`, cut from the front to at most `chars` characters."""
    kept = "\n".join(text.rstrip().splitlines()[-lines:])
    if len(kept) > chars:
        kept = "…" + kept[-(chars - 1):]
    return kept


def read_log(path: str | None) -> str:
    """The end of the log file at `path`; empty when there's none (the step failed before the command ran)."""
    if not path:
        return ""
    try:
        with Path(path).open("rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - _LOG_READ_BYTES))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _one_line(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= _CAUSE_CHARS else line[:_CAUSE_CHARS - 1] + "…"


def _exception_line(lines: list[str]) -> str | None:
    """The exception a traceback ends with: the first line after its frames that isn't indented."""
    for line in lines:
        if line.strip() and not line[0].isspace():
            return line.strip()
    return None


def root_cause(text: str | None) -> str | None:
    """The final exception in a traceback or a log, as one line: "RuntimeError: Ollama is down".

    Reads the last traceback in `text`; when that exception was raised from another, the first is added ("...
    (caused by ConnectError: ...)"). Without a traceback: the end of one cut short (a run's `error` keeps only its
    last 2000 characters), else the log's last error line, else its last line. None for empty text.
    """
    if not text or not text.strip():
        return None
    at = text.rfind(_TRACEBACK)
    if at >= 0:
        cause = _exception_line(text[at + len(_TRACEBACK):].splitlines())
        before = [line.strip() for line in text[:at].splitlines() if line.strip()]
        if cause and len(before) >= 2 and before[-1] in _CHAINED:
            first = before[-2]
            if first != cause and first not in cause:
                cause = f"{cause} (caused by {first})"
        if cause:
            return _one_line(cause)
    lines = [line for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if match := _ERROR_LINE.match(line.strip()):
            message = match["message"]
            for prefix in _LOG_PREFIXES:
                message = message.removeprefix(prefix)
            return _one_line(message)
    unindented = [line for line in lines if not line[0].isspace()]
    return _one_line((unindented or lines)[-1])


# ── when the failure email is due ─────────────────────────────────────────────

def days_since(last_success_at: datetime, now: datetime) -> int:
    return max(0, (now - last_success_at).days)


def failure_due(last_success_at: datetime | None, now: datetime) -> bool:
    """Whether a failure that just happened is worth an email: the last successful ingest finished
    FAILING_AFTER_DAYS ago or more. Never without one (a new database has nothing to have stopped working)."""
    return last_success_at is not None and now - last_success_at >= timedelta(days=FAILING_AFTER_DAYS)


def last_success(db: Session) -> LastSuccess | None:
    # Only these columns: the check job's copy of the database may be behind on migrations when a step failed.
    row = (db.query(IngestionRun.finished_at, IngestionRun.started_at, IngestionRun.edition_title,
                    IngestionRun.edition_date)
           .filter(IngestionRun.status == IngestionStatus.success)
           .order_by(IngestionRun.id.desc()).first())
    if row is None:
        return None
    return LastSuccess(row.finished_at or row.started_at, row.edition_title, row.edition_date)


def _failed_run_error(db: Session) -> str | None:
    """The traceback of the ingestion run that just failed: the newest run, when it's a failure. It's only in this
    job's copy of the database (a failed ingest isn't committed to the data branch)."""
    row = db.query(IngestionRun.status, IngestionRun.error).order_by(IngestionRun.id.desc()).first()
    return row.error if row is not None and row.status == IngestionStatus.failure else None


def actions_run_url(env: Mapping[str, str] | None = None) -> str | None:
    """The GitHub Actions run this is part of; None outside one."""
    env = os.environ if env is None else env
    server, repository, run_id = (env.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repository}/actions/runs/{run_id}" if server and repository and run_id else None


# ── the emails ────────────────────────────────────────────────────────────────

_STYLE = "font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; font-size:14px; color:#18181b"


def _warnings(warnings: list) -> str:
    return f"{len(warnings)} warning{'' if len(warnings) == 1 else 's'}"


def _count(n: int, noun: str) -> str:
    return f"{n} new {noun}{'' if n == 1 else 's'}"


def _html(paragraphs: list[str], facts: list[tuple[str, str]], links: list[tuple[str, str]], log: str = "") -> str:
    e = html.escape
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"></head><body style="{_STYLE}">'
        + "".join(f"<p>{e(p)}</p>" for p in paragraphs)
        + '<table cellpadding="0" cellspacing="0">'
        + "".join(f'<tr><td style="padding:2px 16px 2px 0; color:#52525b; vertical-align:top">{e(k)}</td>'
                  f'<td style="padding:2px 0">{e(v)}</td></tr>' for k, v in facts)
        + "</table>"
        + "".join(f'<p><a href="{e(url)}">{e(label)}</a></p>' for label, url in links)
        + (f'<p>The end of the log:</p><pre style="font-size:12px; background:#f4f4f5; padding:12px; '
           f'white-space:pre-wrap; word-break:break-word">{e(log)}</pre>' if log else "")
        + "</body></html>"
    )


def _text(paragraphs: list[str], facts: list[tuple[str, str]], links: list[tuple[str, str]], log: str = "") -> str:
    lines = [*paragraphs, "", *(f"{k}: {v}" for k, v in facts)]
    for label, url in links:
        lines += ["", f"{label}: {url}"]
    if log:
        lines += ["", "The end of the log:", "-" * 72, log, "-" * 72]
    return "\n".join(lines) + "\n"


def success_email(run: IngestionRun, site: str) -> Notification:
    """The email after a successful ingest: the edition, its Show counts, the new Bands and the new Venues, and its
    warnings."""
    bands, venues = run.new_bands or 0, run.new_venues or 0
    edition = run.edition_title or "the List"
    new_bands = str(bands)
    if bands and run.new_bands_without_photo_pct is not None:
        new_bands += f" ({run.new_bands_without_photo_pct:g}% without a photo)"
    facts = [
        ("Edition", edition + (f" ({run.edition_date.isoformat()})" if run.edition_date else "")),
        ("Shows", f"{run.shows_parsed or 0} parsed, {run.shows_upserted or 0} upserted, {run.shows_new or 0} new"),
        ("New Bands", new_bands),
        ("New Venues", str(venues)),
    ]
    if run.finished_at:
        facts.append(("Finished", f"{run.finished_at:%Y-%m-%d %H:%M} UTC"))
    warnings = run.warnings or []
    facts += [("Warning", w["message"] + (f" ({w['count']} times)" if w.get("count", 1) > 1 else ""))
              for w in warnings]
    paragraphs = [f"The ingest of {edition} succeeded and its data is saved."]
    if warnings:
        paragraphs.append(f"It carried on past {_warnings(warnings)}: what it couldn't do is below.")
    links = [("The site", site)]
    subject = f"The List: ingest succeeded: {_count(bands, 'band')}, {_count(venues, 'venue')}"
    if warnings:
        subject += f", {_warnings(warnings)}"
    return Notification(subject, _text(paragraphs, facts, links), _html(paragraphs, facts, links))


def failure_email(*, stage: str, cause: str, log_tail: str, last: LastSuccess | None, now: datetime,
                  run_url: str | None) -> Notification:
    """The email while the ingest is failing: what failed and why, the last successful ingest, the end of the log."""
    if last is None:
        failing, last_fact = "failing", "never"
    else:
        days = days_since(last.finished_at, now)
        failing = f"failing for {days} days"
        last_fact = (f"{last.finished_at:%Y-%m-%d %H:%M} UTC, {days} days ago"
                     + (f" ({last.edition_title})" if last.edition_title else ""))
    short = cause if len(cause) <= _SUBJECT_CAUSE_CHARS else cause[:_SUBJECT_CAUSE_CHARS - 1] + "…"
    paragraphs = [f"The ingest of the List is {failing}: the {stage} failed again just now. "
                  "This email is sent at most once a day while it keeps failing."]
    facts = [("Root cause", cause), ("Failed stage", stage), ("Last successful ingest", last_fact)]
    links = [("The GitHub Actions run", run_url)] if run_url else []
    return Notification(f"The List: ingest {failing}: {short}",
                        _text(paragraphs, facts, links, log_tail), _html(paragraphs, facts, links, log_tail))


# ── sending ───────────────────────────────────────────────────────────────────

def _configured() -> bool:
    if settings.maintainer_email and settings.resend_api_key:
        return True
    logger.info("notify: skipping, MAINTAINER_EMAIL and RESEND_API_KEY aren't both set")
    return False


def _print(notification: Notification, out: TextIO) -> None:
    to = settings.maintainer_email or "(MAINTAINER_EMAIL isn't set)"
    out.write(f"To: {to}\nSubject: {notification.subject}\n\n{notification.text}")


def _recipient_key() -> str:
    return hashlib.sha256(settings.maintainer_email.strip().lower().encode()).hexdigest()[:16]


def _send(notification: Notification, idempotency_key: str) -> bool:
    """Send to the maintainer. False when Resend had this key already for a different email (409): the day's
    email went out earlier. Raises SendError for any other failure."""
    try:
        post_email(api_key=settings.resend_api_key, sender=settings.alerts_from, to=settings.maintainer_email,
                   subject=notification.subject, html=notification.html, text=notification.text,
                   idempotency_key=idempotency_key)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            return False
        # Resend's answer can quote the request; say only how it failed.
        raise SendError(f"Resend refused the email (HTTP {exc.response.status_code})") from None
    except Exception as exc:
        raise SendError(f"the email couldn't be sent ({type(exc).__name__})") from None
    return True


def notify_success(db: Session, *, dry_run: bool, out: TextIO) -> Notification | None:
    """Email the maintainer about the newest ingestion run, when it succeeded; a dry run prints it to `out`.

    Returns the email, or None when there's nothing to send (no successful newest run, one that brought no new
    Shows and logged no warnings, or not configured).
    """
    run = db.query(IngestionRun).order_by(IngestionRun.id.desc()).first()
    if run is None or run.status != IngestionStatus.success:
        logger.info("notify-success: skipping, the newest ingestion run isn't a successful one")
        return None
    if not run.shows_new and not run.warnings:
        logger.info("notify-success: skipping, the ingest brought no new Shows and logged no warnings")
        return None
    notification = success_email(run, settings.site_url.rstrip("/"))
    if dry_run:
        _print(notification, out)
        return notification
    if not _configured():
        return None
    # One email per run: a re-run of the step is dropped by Resend. The content is in the key because Resend
    # refuses a key reused for a different email.
    content = hashlib.sha256(f"{notification.subject}\n{notification.text}".encode()).hexdigest()[:16]
    _send(notification, f"ingest-success-{run.id}-{_recipient_key()}-{content}")
    logger.info("notify-success: sent (%s)", notification.subject)
    return notification


def notify_failure(db: Session, *, stage: str, log_path: str | None, dry_run: bool, out: TextIO,
                   now: datetime | None = None) -> Notification | None:
    """After a failed check or ingest: email the maintainer when the ingest has been failing for two weeks
    (failure_due), at most once a day. A dry run prints the email to `out`, due or not.

    Returns the email, or None when none was due, the day's had gone already, or it isn't configured.
    """
    now = now or datetime.utcnow()
    last = last_success(db)
    due = failure_due(last.finished_at if last else None, now)
    if not due:
        logger.info("notify-failure: not due, %s",
                    "there's no successful ingest yet" if last is None else
                    f"the last successful ingest was {days_since(last.finished_at, now)} days ago "
                    f"(emails start at {FAILING_AFTER_DAYS})")
        if not dry_run:
            return None

    secrets = _secrets()
    log = read_log(log_path)
    error = _failed_run_error(db) if stage == "ingest" else None
    cause = root_cause(error) or root_cause(log) or f"unknown: the {stage} job failed without a log"
    notification = failure_email(stage=stage, cause=redact(cause, secrets), log_tail=redact(tail(log), secrets),
                                 last=last, now=now, run_url=actions_run_url())
    if dry_run:
        _print(notification, out)
        return notification
    if not _configured():
        return None
    # Once a day (the Bay Area's day): the key is the recipient and the date only. The hourly runs' emails differ,
    # and Resend refuses a key reused for a different email, which is how the rest of the day's are dropped.
    if not _send(notification, f"ingest-failure-{local_today().isoformat()}-{_recipient_key()}"):
        logger.info("notify-failure: today's email went out already")
        return None
    logger.info("notify-failure: sent (failing for %d days)", days_since(last.finished_at, now))
    return notification
