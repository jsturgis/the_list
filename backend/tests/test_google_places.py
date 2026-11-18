"""Google Places (app/ingestion/google_places.py): the city of the place nearest some coordinates."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.ingestion import google_places
from app.ingestion.google_places import PlacesUnavailable, address_city, city_at

_FELTON_MUSIC_HALL = {"addressComponents": [
    {"longText": "6275", "types": ["street_number"]},
    {"longText": "Felton", "types": ["locality", "political"]},
    {"longText": "Santa Cruz County", "types": ["administrative_area_level_2", "political"]},
]}


@pytest.fixture(autouse=True)
def forget():
    """Each test asks Google afresh: city_at keeps its answers."""
    city_at.cache_clear()
    yield
    city_at.cache_clear()


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(google_places.settings, "google_maps_api_key", "test-key")


def _answer(body: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://places.googleapis.com"))


def test_reads_the_city_from_a_places_address():
    assert address_city(_FELTON_MUSIC_HALL) == "Felton"
    assert address_city({"addressComponents": [{"longText": "CA", "types": ["administrative_area_level_1"]}]}) is None


@patch("app.ingestion.google_places.httpx.post")
def test_asks_for_the_nearest_place_and_gives_its_city(post, key):
    post.return_value = _answer({"places": [_FELTON_MUSIC_HALL]})
    assert city_at(37.05134, -122.0733) == "Felton"
    asked = post.call_args.kwargs
    assert post.call_args.args[0].endswith("places:searchNearby")
    assert asked["headers"]["X-Goog-FieldMask"] == "places.addressComponents"   # only what it needs
    assert asked["json"]["rankPreference"] == "DISTANCE"
    assert asked["json"]["locationRestriction"]["circle"]["center"] == {"latitude": 37.05134, "longitude": -122.0733}


@patch("app.ingestion.google_places.httpx.post")
def test_the_same_coordinates_are_asked_about_once(post, key):
    post.return_value = _answer({"places": [_FELTON_MUSIC_HALL]})
    assert city_at(37.05134, -122.0733) == city_at(37.05134, -122.0733) == "Felton"
    assert post.call_count == 1


@patch("app.ingestion.google_places.httpx.post")
def test_no_place_there_is_no_city(post, key):
    post.return_value = _answer({})
    assert city_at(37.05134, -122.0733) is None


@patch("app.ingestion.google_places.httpx.post")
def test_an_error_from_google_is_no_answer_not_no_place(post, key):
    post.return_value = _answer({"error": {"code": 403, "message": "Places API (New) has not been used"}}, 403)
    with pytest.raises(PlacesUnavailable, match="has not been used"):
        city_at(37.05134, -122.0733)


@patch("app.ingestion.google_places.httpx.post", side_effect=httpx.ConnectTimeout("timed out"))
def test_google_not_answering_is_no_answer(post, key):
    with pytest.raises(PlacesUnavailable, match="didn't answer"):
        city_at(37.05134, -122.0733)


def test_without_a_key_google_isnt_asked(monkeypatch):
    monkeypatch.setattr(google_places.settings, "google_maps_api_key", "")
    with pytest.raises(PlacesUnavailable, match="no Google Maps key"):
        city_at(37.05134, -122.0733)
