"""Download the newest formatted edition from a public Google Drive folder.

A Google Apps Script in the maintainer's Drive keeps a fixed `latest.json` file pointing at the newest
edition: {"latest": {"id": ..., "name": ..., "edition_date": ...}}. Both files are shared as "anyone
with the link", so no Google credentials are needed.
"""
from __future__ import annotations

import httpx

from app.config import settings

_DOWNLOAD_URL = "https://drive.google.com/uc"


class DriveError(RuntimeError):
    pass


def _download_json(file_id: str) -> dict:
    response = httpx.get(_DOWNLOAD_URL, params={"export": "download", "id": file_id},
                         follow_redirects=True, timeout=60.0)
    response.raise_for_status()
    if "json" not in response.headers.get("content-type", "") and not response.text.lstrip().startswith("{"):
        raise DriveError(f"Drive file {file_id} is not shared publicly (got a sign-in page, not JSON)")
    return response.json()


def fetch_latest_edition() -> tuple[dict, dict] | tuple[None, None]:
    """Return (edition document, {file_id, file_name}), or (None, None) when there's no edition yet."""
    if not settings.drive_latest_file_id:
        raise DriveError("DRIVE_LATEST_FILE_ID is not set")
    latest = _download_json(settings.drive_latest_file_id).get("latest")
    if not latest or not latest.get("id"):
        return None, None
    return _download_json(latest["id"]), {"file_id": latest["id"], "file_name": latest.get("name")}
