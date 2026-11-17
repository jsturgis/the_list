"""Reading an event's screenshot (app/ingestion/screenshot.py): what the vision model read, as a Show."""
from __future__ import annotations

import base64
import io
import json
from datetime import date
from unittest.mock import patch

import httpx
import pytest
from PIL import Image

from app.ingestion.screenshot import (MAX_PIXELS, ScreenshotError, event_summary, fit, parse_date, read_screenshot,
                                      screenshot_show)
from app.ingestion.upsert import upsert_shows
from app.models.show import AgeRestriction, ShowStatus
from app.models.venue import Region

_TODAY = date(2026, 11, 17)


def _fields(**changes) -> dict:
    """What the model reads from a Bandsintown screenshot."""
    return {"performers": ["Wet Leg", "Idles"], "venue": "The Chapel", "city": "San Francisco, CA",
            "date": "Sat, Dec 5", "doors_time": "7:00 PM", "show_time": "8:00 PM", "price": "$20 - $25",
            "age": "21+", "status": None, **changes}


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


@pytest.mark.parametrize("text, expected", [
    ("Sat, Dec 5", date(2026, 12, 5)),
    ("Saturday, December 5th • 8PM", date(2026, 12, 5)),
    ("Jan 9", date(2027, 1, 9)),           # no year: its next one
    ("Tue Nov 17", _TODAY),
    ("March 1, 2027", date(2027, 3, 1)),
    ("Sept. 3", date(2027, 9, 3)),
    ("5 Dec", date(2026, 12, 5)),
    ("the 5th of December", date(2026, 12, 5)),
    ("12/5", date(2026, 12, 5)),           # US: month first
    ("12/05/26", date(2026, 12, 5)),
    ("2027-02-14", date(2027, 2, 14)),
])
def test_reads_the_date_as_the_screenshot_writes_it(text, expected):
    assert parse_date(text, _TODAY) == expected
    assert screenshot_show(_fields(date=text), _TODAY)["date"] == expected


@pytest.mark.parametrize("text", ["", "Tonight", "Feb 30", "13/45"])
def test_no_date_in_the_text_is_none(text):
    assert parse_date(text, _TODAY) is None


def test_refuses_an_event_that_has_passed():
    with pytest.raises(ScreenshotError, match="has passed"):
        screenshot_show(_fields(date="November 1, 2026"), _TODAY)


def test_one_time_is_the_shows_time():
    data = screenshot_show(_fields(doors_time=None, show_time="2:00 PM"), _TODAY)
    assert (data["door_time"], data["set_time"], data["is_matinee"]) == ("2pm", None, True)


@pytest.mark.parametrize("price, expected", [("Free", "free"), ("$15", "$15"), ("$12.50 adv / $15 dos", "$12.50/$15"),
                                             (None, None), ("Tickets", None)])
def test_reads_the_price(price, expected):
    assert screenshot_show(_fields(price=price), _TODAY)["price_raw"] == expected


def test_reads_all_ages():
    assert screenshot_show(_fields(age="All Ages"), _TODAY)["age_restriction"] == "a/a"


@pytest.mark.parametrize("words, status, sold_out", [
    (None, "upcoming", False),
    ("SOLD OUT", "upcoming", True),
    ("Sold-out", "upcoming", True),
    ("Cancelled", "cancelled", False),
    ("Event canceled", "cancelled", False),
    ("Postponed", "postponed", False),
    ("Low tickets", "upcoming", False),
])
def test_the_events_state_is_what_its_words_say(words, status, sold_out):
    data = screenshot_show(_fields(status=words), _TODAY)
    assert (data["status"], data["is_sold_out"]) == (status, sold_out)


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
    ({"date": None}, "no date on the screenshot$"),
    ({"date": "Tonight"}, "no date on the screenshot \\(read 'Tonight'\\)"),
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


def _png(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, format="PNG")
    return out.getvalue()


@patch("app.ingestion.screenshot.httpx.post")
def test_asks_the_vision_model_with_the_image(post):
    post.return_value = _answer(_fields())
    image = _png(800, 600)

    data = read_screenshot(image, _TODAY)

    request = post.call_args.kwargs["json"]
    assert request["model"] == "qwen2.5vl:3b"
    assert request["format"]["required"][0] == "performers"
    assert request["options"]["num_ctx"] == 8192
    assert request["messages"][0]["images"] == [base64.b64encode(image).decode()]   # small enough as it is
    assert data["bands"] == ["Wet Leg", "Idles"]
    assert data["fields"] == _fields()


def test_a_full_screen_retina_screenshot_is_scaled_down_to_fit_the_models_context():
    with Image.open(io.BytesIO(fit(_png(3456, 2234)))) as smaller:
        width, height = smaller.size
    assert width * height <= MAX_PIXELS
    assert abs(width / height - 3456 / 2234) < 0.01


def test_a_file_that_isnt_an_image_is_refused():
    with pytest.raises(ScreenshotError, match="isn't an image"):
        fit(b"not a png")


@patch("app.ingestion.screenshot.httpx.post")
def test_says_why_ollama_refused(post):
    post.return_value = httpx.Response(400, json={"error": "request (4252 tokens) exceeds the available context size"},
                                       request=httpx.Request("POST", "http://ollama/api/chat"))
    with pytest.raises(ScreenshotError, match="Ollama answered 400: .*exceeds the available context size"):
        read_screenshot(_png(10, 10), _TODAY)


@patch("app.ingestion.screenshot.httpx.post", side_effect=httpx.ConnectError("refused"))
def test_says_when_the_model_cant_be_asked(post):
    with pytest.raises(ScreenshotError, match="couldn't read the screenshot"):
        read_screenshot(_png(10, 10), _TODAY)


@patch("app.ingestion.screenshot.httpx.post")
def test_says_when_the_model_answers_nonsense(post):
    post.return_value = httpx.Response(200, json={"message": {"content": "not json"}},
                                       request=httpx.Request("POST", "http://ollama/api/chat"))
    with pytest.raises(ScreenshotError, match="couldn't read the screenshot"):
        read_screenshot(_png(10, 10), _TODAY)
