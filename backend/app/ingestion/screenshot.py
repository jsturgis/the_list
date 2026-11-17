"""A screenshot of an event (from Bandsintown, Instagram, a venue's site...), for a Show the List doesn't have yet.

Bandsintown turns scripted requests away (Cloudflare), so instead of its page an admin adds a screenshot of the
event on the Admin page, and a vision model on Ollama (settings.vision_model) reads it. `read_screenshot` asks the
model for the event's fields (`read_fields`) and maps them (`screenshot_show`) to a dict for `ingest_shows`, shaped
as a listing from the List is (app/ingestion/steve_list.py), with `source` "screenshot".

The model only reads: what it reads is checked here as an event page's is (a lineup, a Venue in a Bay Area city we
know, a date that isn't past), and anything it couldn't make out is left empty rather than guessed.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date
from typing import Callable

import httpx

from app.config import settings
from app.ingestion.parser import clean_band_name
from app.ingestion.ticketweb import _AGE_RE, _MATINEE_BEFORE, EventError, _clock, _money_range, _parse_clock
from app.ingestion.upsert import known_region

SOURCE = "screenshot"

# What the model is asked for. Its answer is held to this shape (Ollama's structured outputs).
_SCHEMA = {
    "type": "object",
    "properties": {
        "performers": {"type": "array", "items": {"type": "string"}},
        "venue": {"type": ["string", "null"]},
        "city": {"type": ["string", "null"]},
        "year": {"type": ["integer", "null"]},
        "month": {"type": ["integer", "null"]},
        "day": {"type": ["integer", "null"]},
        "doors_time": {"type": ["string", "null"]},
        "show_time": {"type": ["string", "null"]},
        "price": {"type": ["string", "null"]},
        "age": {"type": ["string", "null"]},
        "sold_out": {"type": "boolean"},
        "cancelled": {"type": "boolean"},
    },
    "required": ["performers", "venue", "city", "year", "month", "day", "doors_time", "show_time", "price", "age",
                 "sold_out", "cancelled"],
}
_PROMPT = """This is a screenshot of one live music event. Read the event's details from it, exactly as written.

- performers: every band or artist playing, headliner first, each name exactly as written. Not the tour name,
  not the promoter ("presents"), not the venue.
- venue: the venue's name. city: its city, without the state ("San Francisco", "Oakland").
- year, month, day: the event's date as numbers. year is null when the screenshot doesn't show one.
- doors_time and show_time: as written ("7:00 PM"); doors_time only when it's labelled as doors.
- price: as written, e.g. "$25", "$20 - $25", "Free". age: e.g. "21+", "18+", "All Ages".
- sold_out, cancelled: true only when the screenshot says so.

Use null for anything the screenshot doesn't show. Don't guess."""
_AMOUNT_RE = re.compile(r"\$\s?(\d+(?:\.\d{2})?)")


class ScreenshotError(EventError):
    """The screenshot couldn't be read, or what it shows isn't an upcoming Bay Area event. `fields` is what the
    model read, when it read anything, to show the admin what went wrong."""

    def __init__(self, message: str, fields: dict | None = None):
        super().__init__(message)
        self.fields = fields


def read_fields(image: bytes) -> dict:
    """The event's fields as the vision model reads them from the screenshot (see _SCHEMA)."""
    try:
        response = httpx.post(f"{settings.ollama_base_url}/api/chat", timeout=900.0, json={
            "model": settings.vision_model,
            "stream": False,
            "format": _SCHEMA,
            "options": {"temperature": 0},
            "messages": [{"role": "user", "content": _PROMPT, "images": [base64.b64encode(image).decode()]}],
        })
        response.raise_for_status()
        fields = json.loads(response.json()["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise ScreenshotError(f"couldn't read the screenshot with {settings.vision_model}: {exc}") from exc
    if not isinstance(fields, dict):
        raise ScreenshotError(f"{settings.vision_model} didn't read an event from the screenshot")
    return fields


def read_screenshot(image: bytes, today: date, venue_city: Callable[[str], str | None] = lambda name: None) -> dict:
    """The Show in this screenshot, as a dict for `ingest_shows`, and the fields the model read under "fields"."""
    fields = read_fields(image)
    try:
        return {**screenshot_show(fields, today, venue_city), "fields": fields}
    except ScreenshotError as exc:
        exc.fields = fields
        raise


def _str(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _date(fields: dict, today: date) -> date:
    """The event's date; with no year on the screenshot, its next one on or after today."""
    month, day, year = fields.get("month"), fields.get("day"), fields.get("year")
    try:
        if year:
            return date(int(year), int(month), int(day))
        found = date(today.year, int(month), int(day))
        return found if found >= today else date(today.year + 1, int(month), int(day))
    except (TypeError, ValueError) as exc:
        raise ScreenshotError("no date on the screenshot") from exc


def _price(text: str) -> str | None:
    """The price as the List writes it ("$25", "$20/$25", "free"), which `upsert_shows` reads."""
    if re.search(r"\bfree\b", text, re.IGNORECASE):
        return "free"
    amounts = [float(a) for a in _AMOUNT_RE.findall(text)]
    return _money_range(min(amounts), max(amounts)) if amounts else None


def _age(text: str) -> str | None:
    found = _AGE_RE.search(text)
    return {"all ages": "a/a"}.get(found.group(1).lower(), found.group(1)) if found else None


def screenshot_show(fields: dict, today: date, venue_city: Callable[[str], str | None] = lambda name: None) -> dict:
    """The Show the model read (`fields`, see _SCHEMA) as a dict for `ingest_shows`. With no city on the screenshot,
    `venue_city(name)` gives a known Venue's. Raises ScreenshotError when it isn't an upcoming Bay Area event."""
    seen: set[str] = set()
    bands = []
    for name in (clean_band_name(_str(p)) for p in fields.get("performers") or []):
        if name and name.lower() not in seen:
            seen.add(name.lower())
            bands.append(name)
    if not bands:
        raise ScreenshotError("no lineup on the screenshot")
    venue_name = _str(fields.get("venue"))
    if not venue_name:
        raise ScreenshotError("no venue on the screenshot")
    city = _str(fields.get("city")).split(",")[0].strip() or venue_city(venue_name)
    if known_region(city) is None:
        raise ScreenshotError(f"{venue_name} is in {city or 'an unknown city'}, not a Bay Area city we know")
    when = _date(fields, today)
    if when < today:
        raise ScreenshotError(f"the screenshot's event was on {when:%a %b %-d, %Y}, which has passed")

    door = _parse_clock(_str(fields.get("doors_time")))
    shown = _parse_clock(_str(fields.get("show_time")))
    start = door or shown
    return {
        "source": SOURCE,
        "date": when,
        "bands": bands,
        "act_notes": [None] * len(bands),
        "band_enrichment": [(name, {"genres": []}) for name in bands],
        "venue_name": venue_name,
        "city": city,
        "address": None,
        "venue_website": None,
        "status": "cancelled" if fields.get("cancelled") is True else "upcoming",
        "age_restriction": _age(_str(fields.get("age"))),
        "price_raw": _price(_str(fields.get("price"))),
        # With only one time, it's the Show's time, as for a listing with one time.
        "door_time": _clock(start) if start else None,
        "set_time": _clock(shown) if door and shown else None,
        "notes": None,
        "is_recommended": False,
        "will_sell_out": False,
        "is_pit": False,
        "is_drink_tickets": False,
        "is_no_reentry": False,
        "is_sold_out": fields.get("sold_out") is True,
        "is_matinee": bool(start and start < _MATINEE_BEFORE),
        "is_benefit": False,
        # No ticket link on a screenshot; the Venue's calendar may give one at ingest (app/ingestion/venue_calendar.py).
        "ticket_provider": None,
        "ticket_url": None,
        "raw_text": f"{', '.join(bands)} at {venue_name}, {city} (from a screenshot)",
    }


def event_summary(data: dict) -> str:
    """One line for what was read: "Wet Leg, Idles at The Chapel, San Francisco on Fri Dec 5, 2026"."""
    return f"{', '.join(data['bands'])} at {data['venue_name']}, {data['city']} on {data['date']:%a %b %-d, %Y}"

