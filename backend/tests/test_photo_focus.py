"""Tests for a Band photo's focal point: found from its faces, applied by the site as CSS object-position.

tests/fixtures/face.jpg is a 160px copy of scikit-image's "astronaut" (Eileen Collins, NASA), in the public domain.
"""
from __future__ import annotations

import io
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from app.ingestion.band_photos import fill_photo_focus
from app.ingestion.photo_focus import (
    BANNER_ASPECT, DEFAULT, Face, detect_faces, focus_for, photo_focus, photo_focus_of,
)
from app.models.band import Band

FACE = Path(__file__).parent / "fixtures" / "face.jpg"
BACKEND = Path(__file__).parent.parent


def _face() -> Image.Image:
    with Image.open(FACE) as image:
        return image.convert("RGB")


def _photo(left: int, top: int, size=(800, 450)) -> Image.Image:
    """The face pasted onto a plain backdrop at (left, top): a wide stage photo with its singer off to one side."""
    canvas = Image.new("RGB", size, (40, 40, 60))
    canvas.paste(_face(), (left, top))
    return canvas


def _crop(width: int, height: int, box: tuple[int, int], focus: dict) -> tuple[float, float, float, float]:
    """The part of a `width` × `height` photo (left, top, right, bottom, in its pixels) that object-fit: cover shows
    in a `box`, at object-position `focus`."""
    scale = max(box[0] / width, box[1] / height)
    shown_w, shown_h = box[0] / scale, box[1] / scale
    left, top = (width - shown_w) * focus["x"] / 100, (height - shown_h) * focus["y"] / 100
    return left, top, left + shown_w, top + shown_h


def _whole_in(face: Face, crop) -> bool:
    return crop[0] <= face.x and face.x + face.w <= crop[2] and crop[1] <= face.y and face.y + face.h <= crop[3]


CIRCLE = (64, 64)
BANNER = (672, 288)


def test_a_photo_without_a_face_is_anchored_a_little_above_centre():
    plain = Image.new("RGB", (800, 450), (200, 30, 30))
    assert detect_faces(plain) == []
    assert photo_focus(plain) == DEFAULT == {"x": 50.0, "y": 35.0}


def test_finds_the_face_in_a_real_photo():
    faces = detect_faces(_face())
    assert len(faces) == 1
    face = faces[0]
    # The astronaut's face, in the 160px photo: left of centre, in the top third.
    assert 50 < face.x < 70 and 15 < face.y < 30 and 20 < face.w < 35


@pytest.mark.parametrize("left, expect_x", [(0, lambda x: x < 20), (640, lambda x: x > 80)])
def test_the_focal_point_follows_the_face(left, expect_x):
    photo = _photo(left, 40)
    focus = photo_focus(photo)
    assert expect_x(focus["x"])
    assert focus["y"] < 20  # the face is near the top
    face = detect_faces(photo)[0]
    # Centred, the circle cuts this face off; at the focal point both crops keep it whole.
    assert not _whole_in(face, _crop(800, 450, CIRCLE, {"x": 50, "y": 50}))
    assert _whole_in(face, _crop(800, 450, CIRCLE, focus))
    assert _whole_in(face, _crop(800, 450, BANNER, focus))


def test_a_face_near_the_edge_of_a_wide_photo_stays_whole_in_the_circle():
    # Anywhere across a 2:1 photo, a single face is whole in the square crop and in the banner.
    for x in range(0, 960, 40):
        for y in (0, 150, 400):
            face = Face(x, y, 40, 50, 0.9)
            focus = focus_for([face], 1000, 500)
            assert _whole_in(face, _crop(1000, 500, CIRCLE, focus)), (x, y, focus)
            assert _whole_in(face, _crop(1000, 500, BANNER, focus)), (x, y, focus)


def test_a_face_in_a_tall_photo_stays_whole_in_both_crops():
    for y in range(0, 1150, 50):
        face = Face(300, y, 100, 120, 0.9)
        focus = focus_for([face], 800, 1280)
        assert _whole_in(face, _crop(800, 1280, CIRCLE, focus)), (y, focus)
        assert _whole_in(face, _crop(800, 1280, BANNER, focus)), (y, focus)


def test_a_group_that_fits_is_kept_whole_and_pulled_toward_the_largest_face():
    big, small = Face(400, 50, 80, 100, 0.9), Face(600, 60, 50, 60, 0.95)
    focus = focus_for([small, big], 1000, 500)
    crop = _crop(1000, 500, CIRCLE, focus)
    assert _whole_in(big, crop) and _whole_in(small, crop)
    # Centring the group (x 400–650, a quarter of the photo) in the circle, which shows half of it, would be
    # object-position 55%: (0.525 − 0.25) / (1 − 0.5). Halfway toward the larger face, it's 46.5%.
    assert focus["x"] == 46.5


def test_when_the_faces_dont_fit_the_largest_is_kept_whole():
    largest, other = Face(850, 100, 90, 110, 0.9), Face(20, 100, 80, 100, 0.9)
    focus = focus_for([other, largest], 1000, 500)
    assert _whole_in(largest, _crop(1000, 500, CIRCLE, focus))


def test_faces_in_the_background_are_left_out():
    singer, crowd = Face(100, 100, 100, 120, 0.9), Face(900, 400, 20, 24, 0.9)
    assert focus_for([singer, crowd], 1000, 500) == focus_for([singer], 1000, 500)


def test_an_axis_no_crop_cuts_keeps_the_point_itself():
    # A 3:1 photo is wider than the banner, so neither crop cuts its top and bottom.
    assert 3 > BANNER_ASPECT
    assert focus_for([Face(100, 100, 50, 50, 0.9)], 1500, 500)["y"] == 25.0


def test_the_same_photo_always_gets_the_same_point():
    buf = io.BytesIO()
    _photo(600, 200).save(buf, "WEBP", quality=80)
    data = buf.getvalue()
    assert photo_focus_of(data) == photo_focus_of(data) == photo_focus(Image.open(io.BytesIO(data)))


# The command that fills in existing photos' focal points (python -m app.cli photo-focus)

def _stored(images: Path, db, name: str, image: Image.Image, **kw) -> Band:
    path = f"bands/{name}.webp"
    (images / "bands").mkdir(parents=True, exist_ok=True)
    image.save(images / path, "WEBP")
    band = Band(name=name, genres=[], image_url=path, **kw)
    db.add(band)
    db.flush()
    return band


def test_fill_gives_stored_photos_without_one_their_focal_point(db, tmp_path):
    singer = _stored(tmp_path, db, "Singer", _photo(0, 40))
    plain = _stored(tmp_path, db, "Plain", Image.new("RGB", (800, 450), (9, 9, 9)))
    done = _stored(tmp_path, db, "Done", _photo(0, 40), image_focus={"x": 1.0, "y": 2.0})
    remote = Band(name="Remote", genres=[], image_url="https://img.example/remote.jpg")
    missing = Band(name="Missing", genres=[], image_url="bands/missing.webp")
    db.add_all([remote, missing, Band(name="None", genres=[])])
    db.commit()

    counts = fill_photo_focus(db, tmp_path)

    assert counts == {"bands": 2, "with_faces": 1, "faces": 1, "skipped": 1}
    assert singer.image_focus["x"] < 20 and plain.image_focus == DEFAULT
    assert done.image_focus == {"x": 1.0, "y": 2.0}           # had one: left alone
    assert remote.image_focus is None and missing.image_focus is None
    # Again: nothing left to do. With recompute, every stored photo, to the same points.
    assert fill_photo_focus(db, tmp_path)["bands"] == 0
    before = singer.image_focus
    assert fill_photo_focus(db, tmp_path, recompute=True)["bands"] == 3
    assert singer.image_focus == before and done.image_focus != {"x": 1.0, "y": 2.0}


def test_fill_commits_in_batches(db, tmp_path, monkeypatch):
    for i in range(5):
        _stored(tmp_path, db, f"Band {i}", Image.new("RGB", (80, 45), (i, i, i)))
    db.commit()
    commits = []
    real_commit = db.commit
    monkeypatch.setattr(db, "commit", lambda: commits.append(1) or real_commit())

    fill_photo_focus(db, tmp_path, batch_size=2)

    assert len(commits) == 3  # after the 2nd and 4th Bands, then the rest


# The migration

def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, check=True, capture_output=True)


def _band_columns(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as con:
        return {row[1] for row in con.execute("PRAGMA table_info(bands)")}


def test_the_migration_adds_and_removes_the_focal_point_column(tmp_path):
    # The migrations start from tables the app created, so start from a bands table as it was before this one.
    db_path = tmp_path / "migrated.db"
    with sqlite3.connect(db_path) as con:
        con.execute("CREATE TABLE bands (id INTEGER PRIMARY KEY, name VARCHAR(255), image_url VARCHAR(500), image_credit TEXT)")
        con.execute("INSERT INTO bands VALUES (1, 'Crowbar', 'bands/1-a.webp', NULL)")
    _alembic(db_path, "stamp", "d5a7b9c1e3f4")

    _alembic(db_path, "upgrade", "head")
    assert "image_focus" in _band_columns(db_path)
    with sqlite3.connect(db_path) as con:
        assert con.execute("SELECT name, image_url, image_focus FROM bands").fetchall() == [
            ("Crowbar", "bands/1-a.webp", None)]   # existing photos have none until photo-focus runs

    _alembic(db_path, "downgrade", "d5a7b9c1e3f4")
    assert _band_columns(db_path) == {"id", "name", "image_url", "image_credit"}
