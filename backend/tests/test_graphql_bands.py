"""Tests for bands / band / similarBands / similarShows GraphQL queries."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import numpy as np
import pytest

from app.models.act import Act
from app.models.band import Band
from app.models.show import Show, ShowStatus
from app.models.venue import Region, Venue


# ── helpers ───────────────────────────────────────────────────────────────────

def _venue(db):
    v = Venue(name="The Fillmore", city="San Francisco", region=Region.sf)
    db.add(v)
    db.flush()
    return v


def _show(db, venue, *, show_date=date(2026, 10, 1), status=ShowStatus.upcoming, embedding=None):
    s = Show(date=show_date, venue_id=venue.id, status=status, embedding=embedding)
    db.add(s)
    db.flush()
    return s


def _band(db, name, *, embedding=None, genres=None):
    b = Band(name=name, genres=genres or [], embedding=embedding)
    db.add(b)
    db.flush()
    return b


def _fake_embedding() -> bytes:
    return np.zeros(768, dtype=np.float32).tobytes()


def _gql(client, query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = client.post("/graphql", json=payload)
    assert resp.status_code == 200
    return resp.json()


# ── bands ─────────────────────────────────────────────────────────────────────

def test_bands_partial_name_match(db, client):
    _band(db, "Deafheaven")
    _band(db, "Defeater")
    _band(db, "Motrik")

    body = _gql(client, '{ bands(query: "deaf") { name } }')
    assert "errors" not in body
    names = [b["name"] for b in body["data"]["bands"]]
    assert names == ["Deafheaven"]


def test_bands_case_insensitive(db, client):
    _band(db, "Deafheaven")

    body = _gql(client, '{ bands(query: "DEAF") { name } }')
    assert body["data"]["bands"][0]["name"] == "Deafheaven"


def test_bands_no_match_returns_empty(db, client):
    _band(db, "Motrik")

    body = _gql(client, '{ bands(query: "zzz") { name } }')
    assert body["data"]["bands"] == []


def test_bands_limit(db, client):
    for i in range(5):
        _band(db, f"Band {i:02d}")

    body = _gql(client, '{ bands(query: "Band", limit: 2) { name } }')
    assert len(body["data"]["bands"]) == 2


# ── band ──────────────────────────────────────────────────────────────────────

def test_band_by_id(db, client):
    b = _band(db, "Deafheaven", genres=["black metal", "shoegaze"])

    body = _gql(client, f'{{ band(id: "{b.id}") {{ name genres }} }}')
    assert "errors" not in body
    assert body["data"]["band"]["name"] == "Deafheaven"
    assert body["data"]["band"]["genres"] == ["black metal", "shoegaze"]


def test_band_missing_returns_null(db, client):
    body = _gql(client, '{ band(id: "99") { name } }')
    assert "errors" not in body
    assert body["data"]["band"] is None


# ── similarBands ──────────────────────────────────────────────────────────────

def test_similar_bands_returns_results(db, client):
    b1 = _band(db, "Deafheaven", embedding=_fake_embedding())
    b2 = _band(db, "Alcest")

    with patch("app.graphql.queries.find_similar_bands", return_value=[(b2.id, 0.42)]):
        body = _gql(client, f'{{ similarBands(bandId: "{b1.id}", k: 1) {{ name }} }}')

    assert "errors" not in body
    assert body["data"]["similarBands"][0]["name"] == "Alcest"


def test_similar_bands_preserves_result_order(db, client):
    source = _band(db, "Source", embedding=_fake_embedding())
    b1 = _band(db, "Alpha")
    b2 = _band(db, "Beta")

    with patch("app.graphql.queries.find_similar_bands", return_value=[(b2.id, 0.1), (b1.id, 0.2)]):
        body = _gql(client, f'{{ similarBands(bandId: "{source.id}", k: 2) {{ name }} }}')

    names = [b["name"] for b in body["data"]["similarBands"]]
    assert names == ["Beta", "Alpha"]


def test_similar_bands_excludes_source_band(db, client):
    source = _band(db, "Source", embedding=_fake_embedding())
    b1 = _band(db, "Alpha")
    b2 = _band(db, "Beta")

    # The index returns the source itself as its own nearest neighbour.
    hits = [(source.id, 0.0), (b1.id, 0.1), (b2.id, 0.2)]
    with patch("app.graphql.queries.find_similar_bands", return_value=hits) as mock_search:
        body = _gql(client, f'{{ similarBands(bandId: "{source.id}", k: 2) {{ name }} }}')

    names = [b["name"] for b in body["data"]["similarBands"]]
    assert names == ["Alpha", "Beta"]
    assert mock_search.call_args.args[1] == 3  # over-fetch by one to still return k


def test_similar_bands_no_embedding_returns_empty(db, client):
    b = _band(db, "Deafheaven")  # no embedding

    with patch("app.graphql.queries.find_similar_bands") as mock_search:
        body = _gql(client, f'{{ similarBands(bandId: "{b.id}", k: 5) {{ name }} }}')
        mock_search.assert_not_called()

    assert "errors" not in body
    assert body["data"]["similarBands"] == []


def test_similar_bands_band_not_found_returns_error(client):
    body = _gql(client, '{ similarBands(bandId: "99", k: 1) { name } }')
    assert "errors" in body


# ── similarShows ──────────────────────────────────────────────────────────────

def test_similar_shows_returns_upcoming_only(db, client):
    v = _venue(db)
    source = _show(db, v, embedding=_fake_embedding())
    upcoming = _show(db, v, show_date=date(2026, 10, 2), status=ShowStatus.upcoming)
    cancelled = _show(db, v, show_date=date(2026, 10, 3), status=ShowStatus.cancelled)

    with patch(
        "app.graphql.queries.find_similar_shows",
        return_value=[(upcoming.id, 0.1), (cancelled.id, 0.2)],
    ):
        body = _gql(client, f'{{ similarShows(showId: "{source.id}", k: 5) {{ id status }} }}')

    assert "errors" not in body
    shows = body["data"]["similarShows"]
    assert len(shows) == 1
    assert shows[0]["status"] == "upcoming"


def test_similar_shows_no_embedding_returns_empty(db, client):
    v = _venue(db)
    s = _show(db, v)  # no embedding

    with patch("app.graphql.queries.find_similar_shows") as mock_search:
        body = _gql(client, f'{{ similarShows(showId: "{s.id}", k: 5) {{ id }} }}')
        mock_search.assert_not_called()

    assert "errors" not in body
    assert body["data"]["similarShows"] == []


def test_similar_shows_show_not_found_returns_empty(client):
    body = _gql(client, '{ similarShows(showId: "99", k: 1) { id } }')
    assert "errors" not in body
    assert body["data"]["similarShows"] == []
