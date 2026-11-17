"""Tests for keeping Venue photos with the data: downloaded, stored as WebP, with a Commons photo's credit."""
from __future__ import annotations

import io
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx
from PIL import Image

from app.ingestion.venue_photos import MAX_WIDTH, save_venue_photo, save_venue_photos, store_venue_photos
from app.ingestion.wikimedia import commons_credit
from app.models.venue import Region, Venue

_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
GILMAN = "https://upload.wikimedia.org/wikipedia/commons/d/db/924_Gilman_Street.JPG"
WARFIELD = ("https://thumb.wikimedia.org/wikipedia/commons/thumb/2/26/Warfield_Theatre%2C_SF.JPG/"
            "960px-Warfield_Theatre%2C_SF.JPG")
ELSEWHERE = "https://images.squarespace-cdn.com/content/venue.jpg"
CREDIT = {
    "source": "Wikimedia Commons",
    "author": "Jane Photographer",
    "license": "CC BY-SA 3.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/3.0",
    "source_url": "https://commons.wikimedia.org/wiki/File:924_Gilman_Street.JPG",
}


def _jpeg(width=1600, height=900) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (40, 90, 160)).save(buf, "JPEG")
    return buf.getvalue()


def _imageinfo():
    return {"query": {"pages": {"7": {"title": "File:924 Gilman Street.JPG", "imageinfo": [{
        "url": GILMAN,
        "descriptionurl": CREDIT["source_url"],
        "extmetadata": {
            "Artist": {"value": '<a href="//commons.wikimedia.org/wiki/User:Jane">Jane Photographer</a>'},
            "LicenseShortName": {"value": "CC BY-SA 3.0"},
            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/3.0"},
        },
    }]}}}}


_RealClient = httpx.Client  # tests that replace httpx.Client still build clients with this


def _client(images: dict[str, httpx.Response], commons: httpx.Response | None = None, seen: list | None = None):
    """Answers image downloads from `images` (404 otherwise) and the Commons API with `commons`."""
    def handler(request):
        url = str(request.url)
        if seen is not None:
            seen.append(request)
        if url.startswith(_COMMONS_API):
            return commons or httpx.Response(200, json=_imageinfo())
        return images.get(url, httpx.Response(404))
    return _RealClient(transport=httpx.MockTransport(handler))


def _venue(venue_id=2, image_url=None, image_credit=None):
    return Venue(id=venue_id, name="924 Gilman Street", city="Berkeley", region=Region.east_bay,
                 image_url=image_url, image_credit=image_credit)


def test_a_commons_photo_is_stored_with_its_credit(tmp_path):
    venue = _venue(image_url=GILMAN)
    seen = []

    assert save_venue_photo(venue, GILMAN, tmp_path,
                            _client({GILMAN: httpx.Response(200, content=_jpeg())}, seen=seen)) is True

    assert venue.image_url.startswith("venues/2-") and venue.image_url.endswith(".webp")
    with Image.open(tmp_path / venue.image_url) as saved:
        assert saved.format == "WEBP" and saved.size == (MAX_WIDTH, 450)
    assert venue.image_credit == CREDIT  # the author link reduced to its text
    commons = next(r for r in seen if str(r.url).startswith(_COMMONS_API))
    assert commons.url.params["titles"] == "File:924 Gilman Street.JPG"


def test_a_commons_thumbnail_is_credited_by_its_file(tmp_path):
    seen = []
    commons_credit(WARFIELD, _client({}, seen=seen))
    assert seen[0].url.params["titles"] == "File:Warfield Theatre, SF.JPG"


def test_a_photo_from_elsewhere_is_stored_without_a_credit(tmp_path):
    venue = _venue(image_url=ELSEWHERE)
    seen = []

    assert save_venue_photo(venue, ELSEWHERE, tmp_path,
                            _client({ELSEWHERE: httpx.Response(200, content=_jpeg())}, seen=seen)) is True

    assert venue.image_url.startswith("venues/2-") and venue.image_credit is None
    assert not any(str(r.url).startswith(_COMMONS_API) for r in seen)  # nothing to look up


def test_a_commons_photo_without_its_credit_for_now_is_kept_remote_to_retry(tmp_path):
    venue = _venue(image_url=GILMAN)

    client = _client({GILMAN: httpx.Response(200, content=_jpeg())}, commons=httpx.Response(503))
    assert save_venue_photo(venue, GILMAN, tmp_path, client) is False

    assert venue.image_url == GILMAN and venue.image_credit is None
    assert not list(tmp_path.rglob("*.webp"))  # not stored uncredited


def test_a_gone_photo_is_dropped(tmp_path):
    venue = _venue(image_url=ELSEWHERE)
    assert save_venue_photo(venue, ELSEWHERE, tmp_path, _client({ELSEWHERE: httpx.Response(404)})) is False
    assert venue.image_url is None and venue.image_credit is None


def test_a_temporary_failure_keeps_the_remote_url_to_retry(tmp_path):
    venue = _venue(image_url=ELSEWHERE)
    assert save_venue_photo(venue, ELSEWHERE, tmp_path, _client({ELSEWHERE: httpx.Response(503)})) is False
    assert venue.image_url == ELSEWHERE


def test_a_stored_photo_is_kept_when_its_replacement_fails(tmp_path):
    venue = _venue(image_url=ELSEWHERE)
    save_venue_photo(venue, ELSEWHERE, tmp_path, _client({ELSEWHERE: httpx.Response(200, content=_jpeg())}))
    stored = venue.image_url

    assert save_venue_photo(venue, GILMAN, tmp_path, _client({GILMAN: httpx.Response(404)})) is False
    assert venue.image_url == stored and (tmp_path / stored).exists()


def test_only_venues_with_a_remote_photo_are_downloaded(tmp_path, monkeypatch):
    stored = _venue(venue_id=1, image_url="venues/1-abc.webp")
    remote = _venue(venue_id=2, image_url=ELSEWHERE)
    none = _venue(venue_id=3)
    monkeypatch.setattr(httpx, "Client",
                        lambda **_: _client({ELSEWHERE: httpx.Response(200, content=_jpeg())}))

    assert save_venue_photos([stored, remote, none], tmp_path) == 1

    assert stored.image_url == "venues/1-abc.webp"
    assert remote.image_url.startswith("venues/2-")
    assert none.image_url is None


def test_the_command_stores_every_remote_venue_photo(db, tmp_path, monkeypatch):
    db.add_all([_venue(venue_id=1, image_url=ELSEWHERE), _venue(venue_id=2, image_url=GILMAN),
                _venue(venue_id=3, image_url="https://gone.example/x.jpg")])
    db.commit()
    monkeypatch.setattr(httpx, "Client", lambda **_: _client({
        ELSEWHERE: httpx.Response(200, content=_jpeg()), GILMAN: httpx.Response(503)}))

    assert store_venue_photos(db, tmp_path) == {"pending": 3, "stored": 1, "remote": 1}

    db.expire_all()
    venues = {v.id: v for v in db.query(Venue)}
    assert venues[1].image_url.startswith("venues/1-")
    assert venues[2].image_url == GILMAN       # kept to retry
    assert venues[3].image_url is None         # gone


def test_the_migration_adds_a_venue_photo_credit(tmp_path):
    db_path = tmp_path / "migrated.db"

    def alembic(*args):
        subprocess.run([sys.executable, "-m", "alembic", *args], cwd=Path(__file__).parent.parent, check=True,
                       env={**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}, capture_output=True)

    with sqlite3.connect(db_path) as con:
        con.execute("CREATE TABLE venues (id INTEGER PRIMARY KEY, name VARCHAR(255), image_url VARCHAR(500))")
        con.execute(f"INSERT INTO venues VALUES (1, '924 Gilman Street', '{GILMAN}')")
    alembic("stamp", "f3a5c7e9b1d4")

    alembic("upgrade", "c2e4a6b8d0f1")
    with sqlite3.connect(db_path) as con:
        assert con.execute("SELECT image_url, image_credit FROM venues").fetchall() == [(GILMAN, None)]

    alembic("downgrade", "f3a5c7e9b1d4")
    with sqlite3.connect(db_path) as con:
        assert "image_credit" not in {row[1] for row in con.execute("PRAGMA table_info(venues)")}
