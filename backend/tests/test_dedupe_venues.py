"""Tests for Venue name matching and duplicate-Venue merging."""
from __future__ import annotations

from datetime import date

import pytest

from app.ingestion.dedupe_venues import merge_duplicate_venues, strip_street_from_names
from app.ingestion.upsert import venue_key
from app.models.show import Show
from app.models.venue import Region, Venue


def _venue(db, name, city="Oakland", region=Region.east_bay, **kwargs):
    v = Venue(name=name, city=city, region=region, **kwargs)
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


def test_merge_groups_venues_sharing_a_place_id(db):
    a = _venue(db, "924 Gilman", google_place_id="ChIJgilman")
    b = _venue(db, "924 Gilman Street", google_place_id="ChIJgilman")
    c = _venue(db, "the 924 Gilman St.", google_place_id="ChIJgilman")
    _show(db, b, 1)
    _show(db, b, 2)
    _show(db, c, 3)
    unrelated = _venue(db, "Gilman Brewing", google_place_id="ChIJbrewery")
    db.commit()

    merges = merge_duplicate_venues(db, apply=True)

    assert len(merges) == 1
    assert {v.id for v in merges[0].merged} == {a.id, c.id}
    assert {v.id for v in db.query(Venue).all()} == {b.id, unrelated.id}
    assert {s.venue_id for s in db.query(Show).all()} == {b.id}


def test_name_and_place_links_chain_into_one_group(db):
    # "Fox Theater" ~ "the Fox Theater" by name; "the Fox Theater" ~ "Fox Oakland" by place.
    _venue(db, "Fox Theater")
    _venue(db, "the Fox Theater", google_place_id="ChIJfox")
    _venue(db, "Fox Oakland", google_place_id="ChIJfox")
    db.commit()

    merges = merge_duplicate_venues(db, apply=True)

    assert len(merges) == 1 and len(merges[0].merged) == 2
    assert db.query(Venue).count() == 1


def test_same_name_in_different_regions_is_not_merged(db):
    _venue(db, "the Fox Theater", google_place_id="ChIJoakland")
    _venue(db, "Fox Theater", city="Redwood City", region=Region.sf)
    db.commit()

    assert merge_duplicate_venues(db, apply=True) == []
    assert db.query(Venue).count() == 2


def test_same_name_with_different_place_ids_is_not_merged(db):
    _venue(db, "Music Hall", google_place_id="ChIJone")
    _venue(db, "Music Hall", google_place_id="ChIJtwo")
    db.commit()

    assert merge_duplicate_venues(db, apply=True) == []


def test_street_stripped_from_names_then_merged(db):
    with_street = _venue(db, "Felton Music Hall, 6275 Hwy 9", city="Felton", region=Region.santa_cruz)
    plain = _venue(db, "Felton Music Hall", city="Felton", region=Region.santa_cruz)
    _show(db, plain, 1)
    gilman = _venue(db, "924 Gilman Street", city="Berkeley")
    db.commit()

    renames = strip_street_from_names(db)
    merges = merge_duplicate_venues(db, apply=True)

    assert [(r.old_name, r.venue.name) for r in renames] == [("Felton Music Hall, 6275 Hwy 9", "Felton Music Hall")]
    assert [m.keep.id for m in merges] == [plain.id] and merges[0].merged[0].id == with_street.id
    assert db.get(Venue, gilman.id).name == "924 Gilman Street"


def test_same_show_listed_under_both_venues_is_combined(db):
    from datetime import time
    from app.models.act import Act
    from app.models.band import Band

    keep = _venue(db, "Hopmonk Tavern", google_place_id="ChIJhop")
    dup = _venue(db, "Hopmonk", google_place_id="ChIJhop")
    _show(db, keep, 5)
    a = Show(date=date(2026, 10, 1), venue_id=keep.id, door_time=time(20))
    b = Show(date=date(2026, 10, 1), venue_id=dup.id, door_time=time(20))
    db.add_all([a, b])
    db.flush()
    headliner, opener = Band(name="Headliner"), Band(name="Opener")
    db.add_all([headliner, opener])
    db.flush()
    db.add_all([
        Act(show_id=a.id, band_id=headliner.id, position=0),
        Act(show_id=b.id, band_id=headliner.id, position=0),
        Act(show_id=b.id, band_id=opener.id, position=1),
    ])
    db.commit()

    [merge] = merge_duplicate_venues(db, apply=True)

    assert (merge.shows_moved, merge.shows_combined) == (0, 1)
    assert db.get(Show, b.id) is None
    assert sorted(act.band.name for act in db.get(Show, a.id).acts) == ["Headliner", "Opener"]
