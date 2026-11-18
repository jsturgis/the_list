"""Tell a service that's down from one that has nothing.

The lookups (MusicBrainz, Last.fm, Discogs, Wikimedia Commons, Google Places) return nothing on any failure, so
one Band or Venue never stops a run. But "nothing" from a service that didn't answer isn't "nothing" from one
that doesn't know the Band: a Band looked up during an outage would be marked looked up for good with no genres,
links or photo. Each lookup's `except` block calls `note_failure`, which counts the failure when it's an outage
(no answer, a timeout, a 5xx, a 429, a rejected key), not when the service answered that it has nothing (a 404,
or a reply without the field). The caller compares `failures()` before and after one Band's lookups and, when
any service was down, leaves the Band to be looked up again (app/scheduler.py, app/ingestion/backfill.py).

The counts are process-wide: lookups run in executor threads, which don't see the caller's context variables,
and the ingest and backfill look Bands up one at a time.
"""
from __future__ import annotations

import logging
import threading
from collections import Counter

import httpx

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_failures: Counter[str] = Counter()


class ServiceError(Exception):
    """A service answered with an error of its own (Last.fm's error codes, Google's error object): it couldn't
    answer, rather than having nothing."""


def is_outage(exc: BaseException) -> bool:
    """Whether `exc` means the service couldn't answer, rather than that it has nothing."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code != 404
    if isinstance(exc, (httpx.TransportError, ServiceError, TimeoutError, ConnectionError)):
        return True
    try:
        import musicbrainzngs
    except ImportError:  # pragma: no cover
        return False
    if isinstance(exc, musicbrainzngs.ResponseError):
        return getattr(exc.cause, "code", None) != 404
    return isinstance(exc, musicbrainzngs.NetworkError)


def note_failure(service: str, exc: BaseException) -> None:
    """Count `exc` against `service` if it's an outage (see is_outage). Never raises."""
    if not is_outage(exc):
        return
    with _lock:
        _failures[service] += 1
    logger.warning("%s didn't answer: %s: %s", service, type(exc).__name__, exc)


def failures() -> Counter[str]:
    """Outages counted so far in this process, by service."""
    with _lock:
        return Counter(_failures)

