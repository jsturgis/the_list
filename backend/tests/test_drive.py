"""Tests for downloading the newest formatted edition from a public Google Drive folder."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.drive import DriveError, fetch_latest_edition

POINTER_ID = "pointer123"
EDITION = {"title": "Bay Area & Santa Cruz Concert Events", "edition_date": "2026-09-25", "events": []}


def _response(body, content_type="application/json", status=200):
    r = MagicMock()
    r.status_code = status
    r.headers = {"content-type": content_type}
    r.text = body if isinstance(body, str) else json.dumps(body)
    r.json.side_effect = lambda: json.loads(r.text)
    r.raise_for_status.side_effect = None if status < 400 else RuntimeError(f"HTTP {status}")
    return r


@pytest.fixture
def settings():
    with patch("app.ingestion.drive.settings") as s:
        s.drive_latest_file_id = POINTER_ID
        yield s


def _serve(files: dict):
    """Patch httpx.get to serve {file_id: response} from the public download URL."""
    def get(url, params=None, **kwargs):
        assert url == "https://drive.google.com/uc"
        assert params["export"] == "download"
        assert kwargs.get("follow_redirects") is True
        return files[params["id"]]
    return patch("app.ingestion.drive.httpx.get", side_effect=get)


def test_follows_the_pointer_to_the_newest_edition(settings):
    pointer = {"latest": {"id": "edition456", "name": "Concert Events - September 25, 2026.json",
                          "edition_date": "2026-09-25"}}
    with _serve({POINTER_ID: _response(pointer), "edition456": _response(EDITION)}):
        doc, meta = fetch_latest_edition()

    assert doc == EDITION
    assert meta == {"file_id": "edition456", "file_name": "Concert Events - September 25, 2026.json"}


def test_empty_pointer_means_no_edition(settings):
    with _serve({POINTER_ID: _response({"latest": None})}):
        assert fetch_latest_edition() == (None, None)


def test_file_not_shared_publicly_is_a_clear_error(settings):
    # Drive answers a private file with an HTML sign-in page instead of the JSON.
    with _serve({POINTER_ID: _response("<html>Sign in</html>", content_type="text/html")}):
        with pytest.raises(DriveError, match="not shared publicly"):
            fetch_latest_edition()


def test_missing_pointer_id_fails_before_any_request(settings):
    settings.drive_latest_file_id = ""
    with patch("app.ingestion.drive.httpx.get") as get, pytest.raises(DriveError, match="DRIVE_LATEST_FILE_ID"):
        fetch_latest_edition()
    get.assert_not_called()
