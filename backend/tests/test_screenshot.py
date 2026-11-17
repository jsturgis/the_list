"""Reading an event's screenshot (app/ingestion/screenshot.py): what the vision model read, as a Show."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import httpx
import pytest

from app.ingestion.screenshot import ScreenshotError, event_summary, read_screenshot, screenshot_show
from app.ingestion.upsert import upsert_shows
from app.models.show import AgeRestriction, ShowStatus
from app.models.venue import Region

_TODAY = date(2026, 11, 17)


def _fields(**changes) -> dict:
    """What the model reads from a Bandsintown screenshot."""
    return {"performers": ["Wet Leg", "Idles"], "venue": "The Chapel", "city": "San Francisco, CA", "year": None,
            "month": 12, "day": 5, "doors_time": "7:00 PM", "show_time": "8:00 PM", "price": "$20 - $25",
            "age": "21+", "sold_out": False, "cancelled": False, **changes}


def test_reads_the_show_from_what_the_model_read():
    data = screenshot_show(_fields(), _TODAY)

    assert data["source"] == "screenshot"
    assert data["bands"] == ["Wet Leg", "Idles"]
    assert (data["venue_name"], data["city"]) == ("The Chapel", "San Francisco")
    assert data["date"] == date(2026, 12, 5)
    assert (data["door_time"], data["set_time"]) == ("7pm", "8pm")
    assert (data["price_raw"], data["age_restriction"]) == ("$20/$25", "21+")
    assert (data["status"], data["is_sold_out"], data["is_matinee"]) == ("upcoming", False, False)
    assert data["ticket_url"] is None
    assert event_summary(data) == "Wet Leg, Idles at The Chapel, San Francisco on Sat Dec 5, 2026"


def test_a_date_with_no_year_is_its_next_one():
    assert screenshot_show(_fields(month=1, day=9), _TODAY)["date"] == date(2027, 1, 9)
    assert screenshot_show(_fields(month=11, day=17), _TODAY)["date"] == _TODAY


def test_a_date_with_a_year_is_taken_as_it_is():
    assert screenshot_show(_fields(year=2027, month=3, day=1), _TODAY)["date"] == date(2027, 3, 1)


def test_refuses_an_event_that_has_passed():
    with pytest.raises(ScreenshotError, match="has passed"):
        screenshot_show(_fields(year=2026, month=11, day=1), _TODAY)


def test_one_time_is_the_shows_time():
    data = screenshot_show(_fields(doors_time=None, show_time="2:00 PM"), _TODAY)
    assert (data["door_time"], data["set_time"], data["is_matinee"]) == ("2pm", None, True)


@pytest.mark.parametrize("price, expected", [("Free", "free"), ("$15", "$15"), ("$12.50 adv / $15 dos", "$12.50/$15"),
                                             (None, None), ("Tickets", None)])
def test_reads_the_price(price, expected):
    assert screenshot_show(_fields(price=price), _TODAY)["price_raw"] == expected


def test_reads_all_ages():
    assert screenshot_show(_fields(age="All Ages"), _TODAY)["age_restriction"] == "a/a"


def test_reads_a_cancelled_or_sold_out_event():
    data = screenshot_show(_fields(cancelled=True, sold_out=True), _TODAY)
    assert (data["status"], data["is_sold_out"]) == ("cancelled", True)


def test_drops_repeated_and_empty_performers():
    assert screenshot_show(_fields(performers=["Wet Leg", " ", "wet leg", "Idles"]), _TODAY)["bands"] == ["Wet Leg", "Idles"]


def test_with_no_city_a_known_venues_is_used():
    data = screenshot_show(_fields(city=None), _TODAY, venue_city=lambda name: "Oakland")
    assert data["city"] == "Oakland"


@pytest.mark.parametrize("changes, error", [
    ({"performers": []}, "no lineup"),
    ({"venue": None}, "no venue"),
    ({"city": "Portland"}, "not a Bay Area city"),
    ({"city": None}, "unknown city"),
    ({"month": None}, "no date"),
    ({"month": 2, "day": 30}, "no date"),
])
def test_refuses_what_isnt_an_upcoming_bay_area_event(changes, error):
    with pytest.raises(ScreenshotError, match=error):
        screenshot_show(_fields(**changes), _TODAY)


def test_is_stored_as_a_show_from_a_screenshot(db):
    (show,) = upsert_shows(db, [screenshot_show(_fields(), _TODAY)])

    assert show.source == "screenshot"
    assert [a.band.name for a in show.acts] == ["Wet Leg", "Idles"]
    assert (show.price_min, show.price_max, show.age_restriction) == (20.0, 25.0, AgeRestriction.plus_21)
    assert show.status == ShowStatus.upcoming
    assert show.venue.region == Region.sf


# ── the model ─────────────────────────────────────────────────────────────────

def _answer(fields) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": json.dumps(fields)}},
                          request=httpx.Request("POST", "http://ollama/api/chat"))


@patch("app.ingestion.screenshot.httpx.post")
def test_asks_the_vision_model_with_the_image(post):
    post.return_value = _answer(_fields())

    data = read_screenshot(b"\x89PNG...", _TODAY)

    request = post.call_args.kwargs["json"]
    assert request["model"] == "qwen2.5vl:3b"
    assert request["format"]["required"][0] == "performers"
    assert request["messages"][0]["images"] == ["iVBORy4uLg=="]
    assert data["bands"] == ["Wet Leg", "Idles"]
    assert data["fields"] == _fields()


@patch("app.ingestion.screenshot.httpx.post", side_effect=httpx.ConnectError("refused"))
def test_says_when_the_model_cant_be_asked(post):
    with pytest.raises(ScreenshotError, match="couldn't read the screenshot"):
        read_screenshot(b"png", _TODAY)


@patch("app.ingestion.screenshot.httpx.post")
def test_says_when_the_model_answers_nonsense(post):
    post.return_value = httpx.Response(200, json={"message": {"content": "not json"}},
                                       request=httpx.Request("POST", "http://ollama/api/chat"))
    with pytest.raises(ScreenshotError, match="couldn't read the screenshot"):
        read_screenshot(b"png", _TODAY)
