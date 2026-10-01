"""Tests for the static JSON export (the data contract between backend and frontend)."""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from unittest.mock import patch

import numpy as np
import pytest

from app.clock import local_today
from app.export import export
from app.models.act import Act
from app.models.band import Band
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.models.show import AgeRestriction, Show, ShowStatus
from app.models.venue import Region, Venue

VEC = np.zeros(768, dtype=np.float32).tobytes()


def _venue(db, name="The Fillmore", **kw):
    v = Venue(name=name, city="San Francisco", region=Region.sf, **kw)
    db.add(v)
    db.flush()
    return v


def _band(db, name, **kw):
    b = Band(name=name, genres=kw.pop("genres", ["punk"]), **kw)
    db.add(b)
    db.flush()
    return b


def _show(db, venue, days, bands, status=ShowStatus.upcoming, **kw):
    s = Show(date=local_today() + timedelta(days=days), venue_id=venue.id, status=status, **kw)
    db.add(s)
    db.flush()
    for position, band in enumerate(bands):
        db.add(Act(show_id=s.id, band_id=band.id, position=position))
    db.flush()
    return s


def _gql(client, query):
    resp = client.post("/graphql", json={"query": query})
    assert resp.status_code == 200 and "errors" not in resp.json(), resp.json()
    return resp.json()["data"]


@pytest.fixture
def data(db):
    fillmore = _venue(db, google_place_id="ChIJfillmore", neighborhood="Western Addition", is_cash_only=False)
    chapel = _venue(db, "The Chapel")
    unused_venue = _venue(db, "Closed Venue")
    headliner = _band(db, "Headliner", embedding=VEC, website_url="https://headliner.com", is_local=True)
    support = _band(db, "Support", genres=["noise"])
    past_band = _band(db, "Past Band")
    similar_unexported = _band(db, "Not Playing", embedding=VEC)
    tonight = _show(db, fillmore, 0, [headliner, support], door_time=time(20), price_min=15.0, price_max=20.0,
                    age_restriction=AgeRestriction.plus_21, is_recommended=True, is_sold_out=True,
                    ticket_provider="ticketweb", is_benefit=True, benefit_cause="food drive")
    later = _show(db, chapel, 7, [support], status=ShowStatus.cancelled)
    past = _show(db, fillmore, -1, [past_band])
    db.add(IngestionRun(started_at=datetime(2026, 9, 25, 9), status=IngestionStatus.success,
                        email_subject="Bay Area & Santa Cruz Concert Events — Sep 25, 2026"))
    db.commit()
    return locals()


@pytest.fixture
def exported(db, data, tmp_path):
    hits = [(data["headliner"].id, 0.0), (data["similar_unexported"].id, 0.1), (data["support"].id, 0.2)]
    with patch("app.catalog.find_similar_bands", return_value=hits):
        export(db, tmp_path)
    return {name: json.loads((tmp_path / f"{name}.json").read_text()) for name in ("shows", "venues", "bands", "meta")}


def test_writes_the_four_files(exported):
    assert set(exported) == {"shows", "venues", "bands", "meta"}


def test_shows_from_today_with_fields_and_references(exported, data):
    shows = {s["id"]: s for s in exported["shows"]}
    assert set(shows) == {data["tonight"].id, data["later"].id}  # past Show left out
    s = shows[data["tonight"].id]
    assert s["date"] == local_today().isoformat()
    assert (s["doorTime"], s["setTime"]) == ("20:00:00", None)
    assert (s["priceMin"], s["priceMax"], s["isFree"], s["ageRestriction"], s["status"]) == (15.0, 20.0, False, "21+", "upcoming")
    assert (s["isRecommended"], s["willSellOut"], s["isPit"], s["isDrinkTickets"], s["isNoReentry"]) == (True, False, False, False, False)
    assert (s["isSoldOut"], s["ticketProvider"], s["isBenefit"], s["benefitCause"], s["isMatinee"], s["specialEvent"]) == (
        True, "ticketweb", True, "food drive", False, None)
    assert s["venueId"] == data["fillmore"].id
    assert s["acts"] == [[data["headliner"].id, 0], [data["support"].id, 1]]
    assert shows[data["later"].id]["status"] == "cancelled"


def test_only_referenced_venues_and_bands(exported, data):
    assert {v["id"] for v in exported["venues"]} == {data["fillmore"].id, data["chapel"].id}
    assert {b["id"] for b in exported["bands"]} == {data["headliner"].id, data["support"].id}


def test_venue_and_band_fields(exported, data):
    fillmore = next(v for v in exported["venues"] if v["id"] == data["fillmore"].id)
    assert (fillmore["name"], fillmore["city"], fillmore["region"], fillmore["googlePlaceId"]) == (
        "The Fillmore", "San Francisco", "sf", "ChIJfillmore")
    assert (fillmore["neighborhood"], fillmore["isCashOnly"], fillmore["isSoberSpace"]) == ("Western Addition", False, None)
    headliner = next(b for b in exported["bands"] if b["id"] == data["headliner"].id)
    assert (headliner["name"], headliner["genres"], headliner["websiteUrl"], headliner["isLocal"]) == (
        "Headliner", ["punk"], "https://headliner.com", True)


def test_similar_bands_exclude_self_and_unexported(exported, data):
    headliner = next(b for b in exported["bands"] if b["id"] == data["headliner"].id)
    support = next(b for b in exported["bands"] if b["id"] == data["support"].id)
    assert headliner["similar"] == [data["support"].id]  # self and "Not Playing" dropped
    assert support["similar"] == []  # no embedding


def test_meta_matches_the_graphql_api(exported, client):
    api = _gql(client, """{ filterOptions { regions ages genres dates } showCount
        ingestionRuns(limit: 1, status: "success") { emailSubject } }""")
    meta = exported["meta"]
    assert meta["filterOptions"] == api["filterOptions"]
    assert meta["totalUpcoming"] == api["showCount"] == 1
    assert meta["emailSubject"] == api["ingestionRuns"][0]["emailSubject"]
    assert datetime.fromisoformat(meta["generatedAt"]).tzinfo is not None


def test_an_act_note_is_exported_as_a_third_element(db, data, tmp_path):
    act = db.query(Act).filter(Act.show_id == data["tonight"].id, Act.band_id == data["support"].id).one()
    act.note = "Greg Ginn, Max Zanelly"
    db.commit()
    with patch("app.catalog.find_similar_bands", return_value=[]):
        export(db, tmp_path)
    shows = {s["id"]: s for s in json.loads((tmp_path / "shows.json").read_text())}
    assert shows[data["tonight"].id]["acts"] == [[data["headliner"].id, 0], [data["support"].id, 1, "Greg Ginn, Max Zanelly"]]
