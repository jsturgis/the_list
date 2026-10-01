"""Download the newest formatted edition from a public Google Drive folder.

A Google Apps Script in the maintainer's Drive keeps a fixed `latest.json` file pointing at the newest
edition: {"latest": {"id": ..., "name": ..., "edition_date": ...}}, and optionally the same edition's
enriched export: {"enriched": {"id": ..., "name": ...}}. All are shared as "anyone with the link", so no
Google credentials are needed.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_DOWNLOAD_URL = "https://drive.google.com/uc"


class DriveError(RuntimeError):
    pass


def _download_json(file_id: str) -> dict | list:
    response = httpx.get(_DOWNLOAD_URL, params={"export": "download", "id": file_id},
                         follow_redirects=True, timeout=60.0)
    response.raise_for_status()
    if "json" not in response.headers.get("content-type", "") and not response.text.lstrip().startswith(("{", "[")):
        raise DriveError(f"Drive file {file_id} is not shared publicly (got a sign-in page, not JSON)")
    return response.json()


def _download_enriched(entry: dict | None) -> list[dict]:
    """The enriched export's events, or [] when there's none or it can't be read: it only fills gaps."""
    if not entry or not entry.get("id"):
        return []
    label = entry.get("name") or entry["id"]
    try:
        events = _download_json(entry["id"])
    except Exception as exc:
        logger.warning("drive: skipping enriched export %s: %s", label, exc)
        return []
    if not isinstance(events, list):
        logger.warning("drive: skipping enriched export %s: not a list of events", label)
        return []
    return events


def fetch_latest_edition() -> tuple[dict, dict] | tuple[None, None]:
    """Return (edition document, {file_id, file_name, enriched_events, enriched_file_name}), or (None, None)
    when there's no edition yet. `enriched_events` is [] when the enriched export is missing or unusable."""
    if not settings.drive_latest_file_id:
        raise DriveError("DRIVE_LATEST_FILE_ID is not set")
    pointer = _download_json(settings.drive_latest_file_id)
    latest = pointer.get("latest")
    if not latest or not latest.get("id"):
        return None, None
    doc = _download_json(latest["id"])
    enriched = pointer.get("enriched") or {}
    events = _download_enriched(enriched)
    return doc, {"file_id": latest["id"], "file_name": latest.get("name"), "enriched_events": events,
                 "enriched_file_name": enriched.get("name") if events else None}
