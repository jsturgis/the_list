"""A screenshot of an event (from Bandsintown, Instagram, a venue's site...), for a Show the List doesn't have yet.

Bandsintown turns scripted requests away (Cloudflare), so instead of its page an admin adds a screenshot of the
event on the Admin page, and a vision model on Ollama (settings.vision_model) reads it. `read_fields` asks the model
for the event's fields, copied as the screenshot writes them; `screenshot_show` maps them to a dict for
`ingest_shows`, shaped as a listing from the List is (app/ingestion/steve_list.py), with `source` "screenshot".

A small model invents events where there are none, so nothing it reads is added until an admin has checked it on the
Admin page (and corrected it): app/ingest_jobs.py sends each read screenshot to review, and ingests the fields as
approved. `screenshot_show` checks them as an event page's are (a lineup, a Venue in a Bay Area city we know, a date
that isn't past).
"""
from __future__ import annotations

import base64
import io
import json
import re
from datetime import date
from typing import Callable

import httpx
from PIL import Image, UnidentifiedImageError

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
        "date": {"type": ["string", "null"]},
        "doors_time": {"type": ["string", "null"]},
        "show_time": {"type": ["string", "null"]},
        "price": {"type": ["string", "null"]},
        "age": {"type": ["string", "null"]},
        "status": {"type": ["string", "null"]},
    },
    "required": ["performers", "venue", "city", "date", "doors_time", "show_time", "price", "age", "status"],
}
_PROMPT = """This is a screenshot of one live music event. Read the event's details from it, exactly as written.

- performers: every band or artist playing, headliner first, each name exactly as written. Not the tour name,
  not the promoter ("presents"), not the venue.
- venue: the venue's name. city: its city, without the state ("San Francisco", "Oakland").
- date: the event's date, copied exactly as written ("Fri, Dec 12", "December 12, 2026", "12/12/26").
- doors_time and show_time: as written ("7:00 PM"); doors_time only when it's labelled as doors.
- price: as written, e.g. "$25", "$20 - $25", "Free". age: e.g. "21+", "18+", "All Ages".
- status: words on the screenshot about the event's state, copied exactly ("Sold Out", "Cancelled",
  "Postponed"); null when there are none.

Use null for anything the screenshot doesn't show. Don't guess."""
# The model sees an image as one token per 28×28 pixels, and a full-screen Retina screenshot (3456×2234) is more tokens
# than its default context holds (Ollama answers 400, exceed_context_size_error). Larger screenshots are scaled down
# to this many pixels (about 2,000 tokens), and the context is set to hold them with the prompt and the answer.
MAX_PIXELS = 1_600_000
_CONTEXT_TOKENS = 8192
_AMOUNT_RE = re.compile(r"\$\s?(\d+(?:\.\d{2})?)")


class ScreenshotError(EventError):
    """The screenshot couldn't be read, or what it shows isn't an upcoming Bay Area event. `fields` is what the
    model read, when it read anything, to show the admin what went wrong."""

    def __init__(self, message: str, fields: dict | None = None):
        super().__init__(message)
        self.fields = fields


def fit(image: bytes) -> bytes:
    """The screenshot, scaled down to at most MAX_PIXELS (as a PNG) when it's bigger; as it is otherwise. Every
    screenshot is decoded in full first, so a corrupt or disguised file fails here with a clear reason, not in the
    model; Pillow refuses an image of absurd size (a decompression bomb) as it does."""
    try:
        with Image.open(io.BytesIO(image)) as picture:
            if picture.format not in ("PNG", "JPEG", "WEBP"):
                raise ScreenshotError(f"the screenshot is a {picture.format} image, not a PNG, JPEG or WebP")
            picture.load()
            width, height = picture.size
            if width * height <= MAX_PIXELS:
                return image
            scale = (MAX_PIXELS / (width * height)) ** 0.5
            smaller = picture.convert("RGB").resize((max(1, int(width * scale)), max(1, int(height * scale))),
                                                    Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError, ValueError) as exc:
        raise ScreenshotError(f"the screenshot isn't an image that can be read: {exc}") from exc
    out = io.BytesIO()
    smaller.save(out, format="PNG")
    return out.getvalue()


def read_fields(image: bytes) -> dict:
    """The event's fields as the vision model reads them from the screenshot (see _SCHEMA)."""
    try:
        response = httpx.post(f"{settings.ollama_base_url}/api/chat", timeout=900.0, json={
            "model": settings.vision_model,
            "stream": False,
            "format": _SCHEMA,
            "options": {"temperature": 0, "num_ctx": _CONTEXT_TOKENS},
            "messages": [{"role": "user", "content": _PROMPT, "images": [base64.b64encode(fit(image)).decode()]}],
        })
        if response.is_error:   # Ollama says why in the body ({"error": ...})
            raise ScreenshotError(f"couldn't read the screenshot with {settings.vision_model}: "
                                  f"Ollama answered {response.status_code}: {response.text[:300]}")
        fields = json.loads(response.json()["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise ScreenshotError(f"couldn't read the screenshot with {settings.vision_model}: {exc}") from exc
    if not isinstance(fields, dict):
        raise ScreenshotError(f"{settings.vision_model} didn't read an event from the screenshot")
    return fields


def _str(value) -> str:
    return value.strip() if isinstance(value, str) else ""


_MONTHS = {name: i for i, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?" \
         r"|nov(?:ember)?|dec(?:ember)?)\.?"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s+(\d{4}))?"
_DATE_FORMS = [   # (pattern, which groups are month, day, year)
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), (2, 3, 1)),
    (re.compile(rf"\b{_MONTH}\s+{_DAY}\b{_YEAR}", re.IGNORECASE), (1, 2, 3)),
    (re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MONTH}{_YEAR}", re.IGNORECASE), (2, 1, 3)),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b"), (1, 2, 3)),   # US: month first
]


def parse_date(text: str, today: date) -> date | None:
    """A date as a screenshot shows it ("Fri, Dec 12", "December 12, 2026", "12/12/26", "12 Dec"); with no year,
    its next one on or after today. None when there's no date in it."""
    for pattern, (m, d, y) in _DATE_FORMS:
        found = pattern.search(text)
        if not found:
            continue
        month_text = found.group(m)
        month = int(month_text) if month_text.isdigit() else _MONTHS[month_text[:3].lower()]
        day, year = int(found.group(d)), found.group(y)
        try:
            if year:
                return date(int(year) + (2000 if len(year) == 2 else 0), month, day)
            this_year = date(today.year, month, day)
            return this_year if this_year >= today else date(today.year + 1, month, day)
        except ValueError:
            return None
    return None


def _date(fields: dict, today: date) -> date:
    """The event's date, from the text the model copied off the screenshot."""
    found = parse_date(_str(fields.get("date")), today)
    if found is None:
        raise ScreenshotError(f"no date on the screenshot (read {fields.get('date')!r})" if fields.get("date")
                              else "no date on the screenshot")
    return found


def _price(text: str) -> str | None:
    """The price as the List writes it ("$25", "$20/$25", "free"), which `upsert_shows` reads."""
    if re.search(r"\bfree\b", text, re.IGNORECASE):
        return "free"
    amounts = [float(a) for a in _AMOUNT_RE.findall(text)]
    return _money_range(min(amounts), max(amounts)) if amounts else None


# What a screenshot says about the event's state. The model copies the words, and these decide: a small model asked
# for a yes or no called events sold out that said nothing of the kind.
_SOLD_OUT_RE = re.compile(r"\bsold[\s-]*out\b", re.IGNORECASE)
_CANCELLED_RE = re.compile(r"\bcancel+ed\b", re.IGNORECASE)
_POSTPONED_RE = re.compile(r"\bpostponed\b", re.IGNORECASE)


def _status(text: str) -> str:
    if _CANCELLED_RE.search(text):
        return "cancelled"
    return "postponed" if _POSTPONED_RE.search(text) else "upcoming"


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
        "status": _status(_str(fields.get("status"))),
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
        "is_sold_out": bool(_SOLD_OUT_RE.search(_str(fields.get("status")))),
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

