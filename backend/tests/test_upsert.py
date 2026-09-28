"""Tests for upsert_shows — uses the in-memory SQLite test DB from conftest."""
from __future__ import annotations

from datetime import date

import pytest

from app.ingestion.upsert import upsert_shows
from app.models.act import Act
from app.models.band import Band
from app.models.show import AgeRestriction, Show, ShowStatus
from app.models.venue import Region, Venue


# ── fixtures ──────────────────────────────────────────────────────────────────

def _show(
    *,
    bands: list[str] | None = None,
    venue_name: str = "The Fillmore",
    city: str = "S.F.",
    date_: date = date(2026, 9, 25),
    door_time: str | None = "7pm",
    price_raw: str | None = "$25/$28",
    age_restriction: str | None = "21+",
    status: str = "upcoming",
    **kwargs,
) -> dict:
    return {
        "date": date_,
        "bands": bands if bands is not None else ["Headliner", "Support Act"],
        "venue_name": venue_name,
        "city": city,
        "door_time": door_time,
        "set_time": None,
        "price_raw": price_raw,
        "age_restriction": age_restriction,
        "status": status,
        "is_recommended": False,
        "will_sell_out": False,
        "is_pit": False,
        "is_drink_tickets": False,
        "is_no_reentry": False,
        "ticket_url": None,
        "notes": None,
        "raw_text": "raw",
        "genres": [],
        "spotify_url": None,
        "soundcloud_url": None,
        "venue_website": None,
        "address": None,
        "latitude": None,
        "longitude": None,
        "google_place_id": None,
        **kwargs,
    }


# ── idempotency ───────────────────────────────────────────────────────────────

def test_idempotent_show(db):
    data = [_show()]
    upsert_shows(db, data)
    upsert_shows(db, data)
    assert db.query(Show).count() == 1


def test_idempotent_venue(db):
    data = [_show()]
    upsert_shows(db, data)
    upsert_shows(db, data)
    assert db.query(Venue).count() == 1


def test_idempotent_bands(db):
    data = [_show(bands=["Alpha", "Beta"])]
    upsert_shows(db, data)
    upsert_shows(db, data)
    assert db.query(Band).count() == 2


# ── venue ─────────────────────────────────────────────────────────────────────

def test_venue_city_and_region(db):
    upsert_shows(db, [_show(venue_name="Fox Theater", city="Oakland")])
    v = db.query(Venue).filter(Venue.name == "Fox Theater").one()
    assert v.city == "Oakland"
    assert v.region == Region.east_bay


def test_venue_region_sf(db):
    upsert_shows(db, [_show(city="S.F.")])
    v = db.query(Venue).one()
    assert v.region == Region.sf


def test_venue_region_north_bay(db):
    upsert_shows(db, [_show(venue_name="Phoenix Theater", city="Petaluma")])
    assert db.query(Venue).one().region == Region.north_bay


def test_venue_region_south_bay(db):
    upsert_shows(db, [_show(venue_name="The Ritz", city="San Jose")])
    assert db.query(Venue).one().region == Region.south_bay


def test_venue_region_santa_cruz(db):
    upsert_shows(db, [_show(venue_name="The Catalyst", city="Santa Cruz")])
    assert db.query(Venue).one().region == Region.santa_cruz


def test_venue_region_unknown_defaults_to_sf(db):
    upsert_shows(db, [_show(city="Atlantis")])
    assert db.query(Venue).one().region == Region.sf


def test_venue_website_persisted(db):
    upsert_shows(db, [_show(venue_website="https://thefillmore.com")])
    assert db.query(Venue).one().website_url == "https://thefillmore.com"


def test_venue_google_maps_fields_persisted(db):
    upsert_shows(db, [_show(
        address="1805 Geary Blvd, San Francisco, CA",
        latitude=37.7842,
        longitude=-122.4324,
        google_place_id="ChIJabc123",
    )])
    v = db.query(Venue).one()
    assert v.address == "1805 Geary Blvd, San Francisco, CA"
    assert v.latitude == pytest.approx(37.7842)
    assert v.longitude == pytest.approx(-122.4324)
    assert v.google_place_id == "ChIJabc123"


def test_reuses_existing_venue(db):
    upsert_shows(db, [
        _show(venue_name="Bottom of the Hill", city="S.F.", date_=date(2026, 9, 25)),
        _show(venue_name="Bottom of the Hill", city="S.F.", date_=date(2026, 9, 26)),
    ])
    assert db.query(Venue).count() == 1


# ── price normalisation ───────────────────────────────────────────────────────

def test_price_slash(db):
    upsert_shows(db, [_show(price_raw="$25/$28")])
    s = db.query(Show).one()
    assert s.price_min == pytest.approx(25.0)
    assert s.price_max == pytest.approx(28.0)
    assert s.is_free is False


def test_price_multi_tier(db):
    upsert_shows(db, [_show(price_raw="$25/$27/$30/$35/$40")])
    s = db.query(Show).one()
    assert s.price_min == pytest.approx(25.0)
    assert s.price_max == pytest.approx(40.0)


def test_price_single(db):
    upsert_shows(db, [_show(price_raw="$15")])
    s = db.query(Show).one()
    assert s.price_min == pytest.approx(15.0)
    assert s.price_max == pytest.approx(15.0)


def test_price_free(db):
    upsert_shows(db, [_show(price_raw="free")])
    s = db.query(Show).one()
    assert s.is_free is True
    assert s.price_min == pytest.approx(0.0)
    assert s.price_max == pytest.approx(0.0)


def test_price_missing(db):
    upsert_shows(db, [_show(price_raw=None)])
    s = db.query(Show).one()
    assert s.price_min is None
    assert s.price_max is None
    assert s.is_free is False


# ── age restriction ───────────────────────────────────────────────────────────

def test_age_21_plus(db):
    upsert_shows(db, [_show(age_restriction="21+")])
    assert db.query(Show).one().age_restriction == AgeRestriction.plus_21


def test_age_all_ages(db):
    upsert_shows(db, [_show(age_restriction="a/a")])
    assert db.query(Show).one().age_restriction == AgeRestriction.all_ages


def test_age_unknown(db):
    upsert_shows(db, [_show(age_restriction=None)])
    assert db.query(Show).one().age_restriction == AgeRestriction.unknown


# ── acts / bands ──────────────────────────────────────────────────────────────

def test_acts_positions(db):
    upsert_shows(db, [_show(bands=["Headliner", "Middle", "Opener"])])
    acts = db.query(Act).order_by(Act.position).all()
    assert [a.band.name for a in acts] == ["Headliner", "Middle", "Opener"]
    assert acts[0].position == 0


def test_dj_filtered(db):
    upsert_shows(db, [_show(bands=["Real Band", "dj Aaron Axelsen", "Support"])])
    names = [b.name for b in db.query(Band).all()]
    assert "dj Aaron Axelsen" not in names
    assert "Real Band" in names
    assert "Support" in names


def test_b2b_filtered(db):
    upsert_shows(db, [_show(bands=["Real Band", "Act A b2b Act B"])])
    names = [b.name for b in db.query(Band).all()]
    assert "Act A b2b Act B" not in names
    assert "Real Band" in names


def test_lineup_change_replaces_acts(db):
    base = _show(bands=["Old Headliner", "Old Support"])
    upsert_shows(db, [base])
    assert db.query(Act).count() == 2

    updated = {**base, "bands": ["New Headliner"]}
    upsert_shows(db, [updated])
    acts = db.query(Act).all()
    assert len(acts) == 1
    assert acts[0].band.name == "New Headliner"


def test_shared_band_across_shows(db):
    shared = "Rose City Band"
    upsert_shows(db, [
        _show(bands=[shared, "Rain Parade"], date_=date(2026, 9, 25)),
        _show(bands=[shared, "Motrik"], date_=date(2026, 9, 26)),
    ])
    assert db.query(Band).filter(Band.name == shared).count() == 1
    assert db.query(Show).count() == 2


# ── headliner enrichment ──────────────────────────────────────────────────────

def test_headliner_genres_persisted(db):
    upsert_shows(db, [_show(bands=["Rose City Band", "Rain Parade"], genres=["country rock", "indie"])])
    headliner = db.query(Band).filter(Band.name == "Rose City Band").one()
    support = db.query(Band).filter(Band.name == "Rain Parade").one()
    assert headliner.genres == ["country rock", "indie"]
    assert support.genres == []


def test_headliner_streaming_urls_persisted(db):
    upsert_shows(db, [_show(
        bands=["Beck", "Support"],
        spotify_url="https://open.spotify.com/artist/beck",
        soundcloud_url=None,
    )])
    beck = db.query(Band).filter(Band.name == "Beck").one()
    assert beck.spotify_url == "https://open.spotify.com/artist/beck"


# ── status / flags ────────────────────────────────────────────────────────────

def test_status_cancelled(db):
    upsert_shows(db, [_show(status="cancelled")])
    assert db.query(Show).one().status == ShowStatus.cancelled


def test_flags_persisted(db):
    upsert_shows(db, [_show(
        is_recommended=True, will_sell_out=True,
        is_pit=True, is_drink_tickets=True, is_no_reentry=True,
    )])
    s = db.query(Show).one()
    assert s.is_recommended and s.will_sell_out and s.is_pit
    assert s.is_drink_tickets and s.is_no_reentry
