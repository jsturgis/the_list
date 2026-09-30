"""Tests for Venue name matching and duplicate-Venue merging."""
from __future__ import annotations

from datetime import date

import pytest

from app.ingestion.dedupe_venues import merge_duplicate_venues
from app.ingestion.upsert import venue_key
from app.models.show import Show
from app.models.venue import Region, Venue


def _venue(db, name, **kwargs):
    v = Venue(name=name, city="Oakland", region=Region.east_bay, **kwargs)
    db.add(v)
    db.flush()
    return v


def _show(db, venue, day):
    s = Show(date=date(2026, 10, day), venue_id=venue.id)
    db.add(s)
    db.flush()
    return s


@pytest.mark.parametrize("name, key", [
    ("the Fox Theater", "fox theater"),
    ("Fox Theater", "fox theater"),
    ("Neck Of The Woods", "neck of the woods"),
    ("  The   Planetarium ", "planetarium"),
    ("Theater of Dreams", "theater of dreams"),  # "the" must be a whole word
])
def test_venue_key(name, key):
    assert venue_key(name) == key


def test_merge_keeps_venue_with_most_shows_and_moves_the_rest(db):
    small = _venue(db, "Fox Theater", phone="(510) 302-2250")
    big = _venue(db, "the Fox Theater", address="1807 Telegraph Ave")
    _show(db, small, 1)
    _show(db, big, 2)
    _show(db, big, 3)
    other = _venue(db, "Ivy Room")
    db.commit()

    merges = merge_duplicate_venues(db, apply=True)

    assert len(merges) == 1 and merges[0].shows_moved == 1
    venues = {v.id: v for v in db.query(Venue).all()}
    assert set(venues) == {big.id, other.id}
    kept = venues[big.id]
    assert kept.address == "1807 Telegraph Ave"
    assert kept.phone == "(510) 302-2250"  # filled from the duplicate
    assert {s.venue_id for s in db.query(Show).all()} == {big.id}


def test_merge_dry_run_changes_nothing(db):
    a = _venue(db, "Fox Theater")
    b = _venue(db, "the Fox Theater")
    _show(db, a, 1)
    db.commit()

    merges = merge_duplicate_venues(db, apply=False)

    assert len(merges) == 1
    db.expire_all()
    assert db.query(Venue).count() == 2
    assert db.query(Show).one().venue_id == a.id
