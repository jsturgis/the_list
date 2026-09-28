"""Tests for the shows / show GraphQL queries."""
from __future__ import annotations

import json
from datetime import date

import pytest

from app.models.act import Act
from app.models.band import Band
from app.models.show import AgeRestriction, Show, ShowStatus
from app.models.venue import Region, Venue


# ── seeding helpers ───────────────────────────────────────────────────────────

def _venue(db, *, name="The Fillmore", city="San Francisco", region=Region.sf):
    v = Venue(name=name, city=city, region=region)
    db.add(v)
    db.flush()
    return v


def _show(db, venue, *, show_date=date(2026, 10, 1), status=ShowStatus.upcoming, **kwargs):
    s = Show(date=show_date, venue_id=venue.id, status=status, **kwargs)
    db.add(s)
    db.flush()
    return s


def _band(db, name="Test Band", genres=None):
    b = Band(name=name, genres=genres or [])
    db.add(b)
    db.flush()
    return b


def _act(db, show, band, position=0):
    a = Act(show_id=show.id, band_id=band.id, position=position)
    db.add(a)
    db.flush()
    return a


def _gql(client, query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = client.post("/graphql", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "errors" not in body, body.get("errors")
    return body["data"]


# ── shows: basic ─────────────────────────────────────────────────────────────

def test_shows_returns_upcoming_by_default(db, client):
    v = _venue(db)
    _show(db, v, status=ShowStatus.upcoming)
    _show(db, v, show_date=date(2026, 10, 2), status=ShowStatus.cancelled)

    data = _gql(client, "{ shows { id status } }")
    assert len(data["shows"]) == 1
    assert data["shows"][0]["status"] == "upcoming"


def test_shows_empty_when_none(db, client):
    data = _gql(client, "{ shows { id } }")
    assert data["shows"] == []


def test_show_by_id(db, client):
    v = _venue(db)
    s = _show(db, v)

    data = _gql(client, f'{{ show(id: "{s.id}") {{ id date }} }}')
    assert int(data["show"]["id"]) == s.id
    assert data["show"]["date"] == "2026-10-01"


def test_show_nonexistent_returns_null(db, client):
    data = _gql(client, '{ show(id: "99") { id } }')
    assert data["show"] is None


# ── shows: date filters ───────────────────────────────────────────────────────

def test_from_date_filter(db, client):
    v = _venue(db)
    _show(db, v, show_date=date(2026, 9, 30))
    _show(db, v, show_date=date(2026, 10, 1))
    _show(db, v, show_date=date(2026, 10, 2))

    data = _gql(client, '{ shows(filters: { fromDate: "2026-10-01" }) { date } }')
    dates = [s["date"] for s in data["shows"]]
    assert "2026-09-30" not in dates
    assert "2026-10-01" in dates
    assert "2026-10-02" in dates


def test_to_date_filter(db, client):
    v = _venue(db)
    _show(db, v, show_date=date(2026, 10, 1))
    _show(db, v, show_date=date(2026, 10, 2))
    _show(db, v, show_date=date(2026, 10, 3))

    data = _gql(client, '{ shows(filters: { toDate: "2026-10-02" }) { date } }')
    dates = [s["date"] for s in data["shows"]]
    assert "2026-10-03" not in dates
    assert "2026-10-01" in dates
    assert "2026-10-02" in dates


# ── shows: venue filters ──────────────────────────────────────────────────────

def test_city_filter_case_insensitive(db, client):
    sf = _venue(db, city="San Francisco", region=Region.sf)
    oak = _venue(db, name="Fox Theater", city="Oakland", region=Region.east_bay)
    _show(db, sf)
    _show(db, oak, show_date=date(2026, 10, 2))

    data = _gql(client, '{ shows(filters: { city: "san francisco" }) { venue { city } } }')
    assert len(data["shows"]) == 1
    assert data["shows"][0]["venue"]["city"] == "San Francisco"


def test_region_filter(db, client):
    sf = _venue(db, city="San Francisco", region=Region.sf)
    oak = _venue(db, name="Fox", city="Oakland", region=Region.east_bay)
    _show(db, sf)
    _show(db, oak, show_date=date(2026, 10, 2))

    data = _gql(client, '{ shows(filters: { region: "east_bay" }) { venue { region } } }')
    assert len(data["shows"]) == 1
    assert data["shows"][0]["venue"]["region"] == "east_bay"


# ── shows: band filter ────────────────────────────────────────────────────────

def test_band_name_partial_match(db, client):
    v = _venue(db)
    s1 = _show(db, v, show_date=date(2026, 10, 1))
    s2 = _show(db, v, show_date=date(2026, 10, 2))
    b1 = _band(db, "Rose City Band")
    b2 = _band(db, "Motrik")
    _act(db, s1, b1)
    _act(db, s2, b2)

    data = _gql(client, '{ shows(filters: { bandName: "rose" }) { acts { band { name } } } }')
    assert len(data["shows"]) == 1
    assert data["shows"][0]["acts"][0]["band"]["name"] == "Rose City Band"


# ── shows: price filters ──────────────────────────────────────────────────────

def test_price_max_filter(db, client):
    v = _venue(db)
    _show(db, v, show_date=date(2026, 10, 1), price_min=15.0, price_max=20.0)
    _show(db, v, show_date=date(2026, 10, 2), price_min=30.0, price_max=35.0)

    data = _gql(client, "{ shows(filters: { priceMax: 20 }) { priceMin } }")
    assert len(data["shows"]) == 1
    assert data["shows"][0]["priceMin"] == 15.0


def test_is_free_filter(db, client):
    v = _venue(db)
    _show(db, v, show_date=date(2026, 10, 1), is_free=True, price_min=0.0, price_max=0.0)
    _show(db, v, show_date=date(2026, 10, 2), is_free=False, price_min=20.0)

    data = _gql(client, "{ shows(filters: { isFree: true }) { isFree } }")
    assert len(data["shows"]) == 1
    assert data["shows"][0]["isFree"] is True


# ── shows: misc filters ───────────────────────────────────────────────────────

def test_age_restriction_filter(db, client):
    v = _venue(db)
    _show(db, v, show_date=date(2026, 10, 1), age_restriction=AgeRestriction.all_ages)
    _show(db, v, show_date=date(2026, 10, 2), age_restriction=AgeRestriction.plus_21)

    data = _gql(client, '{ shows(filters: { ageRestriction: "a/a" }) { ageRestriction } }')
    assert len(data["shows"]) == 1
    assert data["shows"][0]["ageRestriction"] == "a/a"


def test_is_recommended_filter(db, client):
    v = _venue(db)
    _show(db, v, show_date=date(2026, 10, 1), is_recommended=True)
    _show(db, v, show_date=date(2026, 10, 2), is_recommended=False)

    data = _gql(client, "{ shows(filters: { isRecommended: true }) { isRecommended } }")
    assert len(data["shows"]) == 1
    assert data["shows"][0]["isRecommended"] is True


def test_status_cancelled_filter(db, client):
    v = _venue(db)
    _show(db, v, show_date=date(2026, 10, 1), status=ShowStatus.upcoming)
    _show(db, v, show_date=date(2026, 10, 2), status=ShowStatus.cancelled)

    data = _gql(client, '{ shows(filters: { status: "cancelled" }) { status } }')
    assert len(data["shows"]) == 1
    assert data["shows"][0]["status"] == "cancelled"


# ── shows: pagination ─────────────────────────────────────────────────────────

def test_limit(db, client):
    v = _venue(db)
    for i in range(5):
        _show(db, v, show_date=date(2026, 10, i + 1))

    data = _gql(client, "{ shows(limit: 2) { id } }")
    assert len(data["shows"]) == 2


def test_offset(db, client):
    v = _venue(db)
    for i in range(4):
        _show(db, v, show_date=date(2026, 10, i + 1))

    all_ids = [s["id"] for s in _gql(client, "{ shows { id } }")["shows"]]
    paged = [s["id"] for s in _gql(client, "{ shows(offset: 2) { id } }")["shows"]]
    assert paged == all_ids[2:]


# ── shows: nested fields ──────────────────────────────────────────────────────

def test_nested_venue_fields(db, client):
    v = _venue(db, name="The Fillmore", city="San Francisco", region=Region.sf)
    _show(db, v)

    data = _gql(client, "{ shows { venue { id name city region } } }")
    venue = data["shows"][0]["venue"]
    assert venue["name"] == "The Fillmore"
    assert venue["city"] == "San Francisco"
    assert venue["region"] == "sf"


def test_nested_acts_and_band(db, client):
    v = _venue(db)
    s = _show(db, v)
    b1 = _band(db, "Rose City Band", genres=["country rock", "indie"])
    b2 = _band(db, "Support Act")
    _act(db, s, b1, position=0)
    _act(db, s, b2, position=1)

    data = _gql(client, "{ shows { acts { position band { name genres spotifyUrl } } } }")
    acts = data["shows"][0]["acts"]
    assert acts[0]["position"] == 0
    assert acts[0]["band"]["name"] == "Rose City Band"
    assert acts[0]["band"]["genres"] == ["country rock", "indie"]
    assert acts[1]["band"]["name"] == "Support Act"


def test_all_flag_fields(db, client):
    v = _venue(db)
    _show(
        db, v,
        is_recommended=True, will_sell_out=True,
        is_pit=True, is_drink_tickets=True, is_no_reentry=True,
    )

    data = _gql(client, "{ shows { isRecommended willSellOut isPit isDrinkTickets isNoReentry } }")
    s = data["shows"][0]
    assert s["isRecommended"] and s["willSellOut"] and s["isPit"]
    assert s["isDrinkTickets"] and s["isNoReentry"]
