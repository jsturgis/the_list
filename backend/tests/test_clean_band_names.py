"""Tests for cleaning Band names that include set times or show details."""
from __future__ import annotations

from datetime import date

import pytest

from app.ingestion.clean_band_names import clean_band_names
from app.ingestion.parser import clean_band_name
from app.models.act import Act
from app.models.band import Band
from app.models.show import Show
from app.models.venue import Region, Venue


@pytest.mark.parametrize("raw, clean", [
    ("The Coverups (2:30pm)", "The Coverups"),
    ("Sisto (midnight)", "Sisto"),
    ("Brassica a/a $20 8pm", "Brassica"),
    ("Set Me Free", "Set Me Free"),
    ("TheArti$t", "TheArti$t"),
    ("Salt +", "Salt +"),
    ("Blink-182", "Blink-182"),
])
def test_clean_band_name(raw, clean):
    assert clean_band_name(raw) == clean


def _show(db, day):
    v = db.query(Venue).first() or Venue(name="Ivy Room", city="Albany", region=Region.east_bay)
    s = Show(date=date(2026, 10, day), venue=v)
    db.add(s)
    db.flush()
    return s


def _band(db, name, *shows):
    b = Band(name=name)
    db.add(b)
    db.flush()
    for s in shows:
        db.add(Act(show_id=s.id, band_id=b.id, position=0))
    db.flush()
    return b


def test_renames_when_no_clean_band_exists(db):
    b = _band(db, "Brassica a/a $20 8pm", _show(db, 10))
    db.commit()

    clean_band_names(db, apply=True)

    assert db.get(Band, b.id).name == "Brassica"


def test_merges_into_existing_band_and_drops_duplicate_act(db):
    s1, s2 = _show(db, 1), _show(db, 2)
    real = _band(db, "Trap Girl", s1)
    bad = _band(db, "Trap Girl (5pm)", s1, s2)  # s1 would list Trap Girl twice after merge
    db.commit()

    fixes = clean_band_names(db, apply=True)

    assert [f.merged_into_existing for f in fixes] == [True]
    assert db.get(Band, bad.id) is None
    assert sorted(a.show_id for a in db.query(Act).filter(Act.band_id == real.id)) == [s1.id, s2.id]
    assert db.query(Act).count() == 2


def test_dry_run_changes_nothing(db):
    b = _band(db, "Sisto (midnight)", _show(db, 16))
    db.commit()

    clean_band_names(db, apply=False)

    db.expire_all()
    assert db.get(Band, b.id).name == "Sisto (midnight)"
