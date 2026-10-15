"""Tests for merging Bands stored twice under different spellings."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np

from app.embeddings.indexer import load_or_create_index, remove_from_index, save_index
from app.ingestion.dedupe_bands import merge_duplicate_bands, saved_filters_pinning
from app.models.act import Act
from app.models.band import Band
from app.models.show import Show
from app.models.venue import Region, Venue


def _band(db, name, **kwargs):
    b = Band(name=name, **kwargs)
    db.add(b)
    db.flush()
    return b


def _show(db, day, *bands):
    venue = db.query(Venue).first() or Venue(name="Ivy Room", city="Albany", region=Region.east_bay)
    s = Show(date=date(2026, 10, day), venue=venue)
    db.add(s)
    db.flush()
    for position, band in enumerate(bands):
        db.add(Act(show_id=s.id, band_id=band.id, position=position))
    db.flush()
    return s


def test_merge_keeps_the_band_with_most_acts_and_moves_the_rest(db):
    few = _band(db, "Fake YOur Own Death")
    most = _band(db, "Fake Your Own Death")
    other = _band(db, "Fog City Ramblers")
    one = _show(db, 1, few)
    _show(db, 2, most, other)
    _show(db, 3, most)
    db.commit()

    merges = merge_duplicate_bands(db, apply=True)

    assert [(m.keep.id, [d.id for d in m.merged]) for m in merges] == [(most.id, [few.id])]
    assert {b.id for b in db.query(Band).all()} == {most.id, other.id}
    assert db.get(Show, one.id).acts[0].band_id == most.id


def test_a_show_listing_both_spellings_keeps_one_act_where_the_first_was(db):
    keep = _band(db, "Da Pupz")
    dup = _band(db, "Da Pupz!")
    other = _band(db, "Opener")
    _show(db, 2, keep)
    both = _show(db, 1, dup, other, keep)
    db.commit()

    merge_duplicate_bands(db, apply=True)

    db.expire_all()
    assert [(a.band_id, a.position) for a in db.get(Show, both.id).acts] == [(keep.id, 0), (other.id, 1)]


def test_on_equal_acts_an_enriched_band_is_kept_then_the_lowest_id(db):
    first = _band(db, "Step Up")
    enriched = _band(db, "STep Up", enriched_at=datetime(2026, 10, 1))
    low = _band(db, "Swept to Sea")
    high = _band(db, "Swept To Sea")
    for day, band in enumerate([first, enriched, low, high], start=1):
        _show(db, day, band)
    db.commit()

    kept = {m.keep.id for m in merge_duplicate_bands(db, apply=True)}

    assert kept == {enriched.id, low.id}


def test_the_kept_band_takes_the_others_details_where_it_has_none(db):
    keep = _band(db, "Swept to Sea", genres=["shoegaze"], description="Oakland shoegaze.", is_local=False)
    dup = _band(db, "Swept To Sea", genres=["dream pop"], description="Other words.", website_url="https://swept.example",
                links=[{"type": "bandcamp", "url": "https://swept.bandcamp.com"}], members=[{"name": "Ana", "active": True}],
                image_url="bands/2-a.webp", image_credit={"source": "Discogs"}, image_focus={"x": 10.0, "y": 0.0},
                embedding=b"\x00" * 4, enriched_at=datetime(2026, 10, 1), is_local=True)
    _show(db, 1, keep)
    _show(db, 2, keep)
    _show(db, 3, dup)
    db.commit()

    merge_duplicate_bands(db, apply=True)

    band = db.get(Band, keep.id)
    assert (band.genres, band.description, band.is_local) == (["shoegaze"], "Oakland shoegaze.", False)  # its own are kept
    assert band.website_url == "https://swept.example"
    assert band.links == [{"type": "bandcamp", "url": "https://swept.bandcamp.com"}]
    assert band.members == [{"name": "Ana", "active": True}]
    # A photo goes with its credit and focal point.
    assert (band.image_url, band.image_credit, band.image_focus) == ("bands/2-a.webp", {"source": "Discogs"}, {"x": 10.0, "y": 0.0})
    assert (band.embedding, band.enriched_at) == (b"\x00" * 4, datetime(2026, 10, 1))


def test_a_kept_photo_keeps_its_own_credit_and_focal_point(db):
    keep = _band(db, "Swept to Sea", image_url="bands/1-a.webp", image_credit=None, image_focus=None)
    dup = _band(db, "Swept To Sea", image_url="bands/2-b.webp", image_credit={"source": "Discogs"}, image_focus={"x": 1.0, "y": 2.0})
    _show(db, 1, keep)
    _show(db, 2, keep)
    _show(db, 3, dup)
    db.commit()

    merge_duplicate_bands(db, apply=True)

    band = db.get(Band, keep.id)
    assert (band.image_url, band.image_credit, band.image_focus) == ("bands/1-a.webp", None, None)


def test_a_dry_run_says_what_it_would_merge_and_changes_nothing(db):
    keep = _band(db, "B.F.H.")
    dup = _band(db, "B.F.H")
    _show(db, 1, keep)
    _show(db, 2, keep)
    _show(db, 3, dup)
    db.commit()

    [merge] = merge_duplicate_bands(db)

    assert merge.summary == f"keep {keep.id}:'B.F.H.' <- {dup.id}:'B.F.H'"
    assert db.query(Band).count() == 2
    assert {a.band_id for a in db.query(Act).all()} == {keep.id, dup.id}


def test_lists_the_saved_filters_that_pin_a_merged_band():
    rows = [
        {"user_id": "u1", "name": "B.F.H", "query": "bandId=2214"},
        {"user_id": "u2", "name": "Punk in the East Bay", "query": "genre=punk&region=east_bay"},
        {"user_id": "u3", "name": "B.F.H. again", "query": "region=sf&bandId=982"},
        {"user_id": "u4", "name": "Not a merged one", "query": "bandId=22140"},
    ]
    assert saved_filters_pinning({2214, 982}, rows) == [rows[0], rows[2]]


def test_removing_bands_from_a_saved_index_keeps_the_rest(tmp_path):
    path = str(tmp_path / "bands.index")
    index = load_or_create_index(path, 4)
    index.add_with_ids(np.eye(3, 4, dtype=np.float32), np.array([1, 2, 3], dtype=np.int64))
    save_index(index, path)

    remove_from_index(path, [2])

    _, ids = load_or_create_index(path, 4).search(np.eye(3, 4, dtype=np.float32)[:1], 3)
    assert sorted(i for i in ids[0] if i >= 0) == [1, 3]


def test_removing_from_an_index_that_was_never_saved_does_nothing(tmp_path):
    remove_from_index(str(tmp_path / "bands.index"), [2])
    assert not (tmp_path / "bands.index").exists()
