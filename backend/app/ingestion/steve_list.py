"""Steve's List as he publishes it: the plain-text page at https://stevelist.com/list, the source of every Show.

`fetch_list` downloads the page; `list_shows` maps its listings (app/ingestion/parser.py) to dicts ready for
`upsert_shows`. The page says which Shows there are, where and when, and Steve's flags and notes; everything
else about a Band or Venue comes from the services.

An edition is the page as of the date in its header. Steve also corrects the page between editions, so a page is
told from the last one ingested by its hash (`ListPage.sha256`), and an edition by its date.
"""
from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass
from datetime import date, time

import httpx

from app.config import settings
from app.ingestion.parser import RawShow, edition_date, parse_list
from app.ingestion.upsert import _CITY_REGION, _parse_time

# Fewer listings than this isn't the List (it has hundreds): a page cut short, or one that has changed shape.
_MIN_SHOWS = 20
# Steve's own names for a city, and the one it goes by here.
_CITY_NAMES = {"s.f.": "San Francisco", "sf": "San Francisco"}
_CITIES = sorted(_CITY_REGION, key=len, reverse=True)
_MATINEE_BEFORE = time(17, 0)
_SOLD_OUT_RE = re.compile(r"\bsold[ -]?out\b", re.IGNORECASE)
_BENEFIT_RE = re.compile(r"\b(?:benefit|fundraiser)\b", re.IGNORECASE)


class ListError(RuntimeError):
    """The page couldn't be fetched, or isn't the List."""


@dataclass(frozen=True)
class ListPage:
    text: str
    sha256: str          # of the page as served: changes whenever Steve changes anything
    edition_date: date   # the date in its header


def fetch_list() -> ListPage:
    """The List as it is now."""
    try:
        response = httpx.get(settings.list_url, follow_redirects=True, timeout=60.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ListError(f"couldn't fetch {settings.list_url}: {exc}") from exc
    return list_page(response.content)


def list_page(content: bytes) -> ListPage:
    text = content.decode("utf-8", errors="replace")
    try:
        edition = edition_date(text)
    except ValueError as exc:
        raise ListError(f"{settings.list_url} isn't the List: {exc}") from exc
    return ListPage(text=text, sha256=hashlib.sha256(content).hexdigest(), edition_date=edition)


def edition_title(edition: date) -> str:
    """What an edition is called on the site and on its ingestion run: "The List for Nov 13, 2026"."""
    return f"The List for {edition.strftime('%b')} {edition.day}, {edition.year}"


def list_shows(text: str) -> list[dict]:
    """One upsert-ready dict per listing. Raises ListError when the text has too few to be the List."""
    shows = [_show(raw) for raw in parse_list(text) if raw.venue_name]
    if len(shows) < _MIN_SHOWS:
        raise ListError(f"only {len(shows)} listings in the List; expected at least {_MIN_SHOWS}")
    return shows


def _known_city(words: list[str]) -> tuple[str, int] | None:
    """(city, how many of `words` it took) when `words` starts with a city we know, typos allowed ("Oaland")."""
    for count in range(min(3, len(words)), 0, -1):
        candidate = " ".join(words[:count]).lower().rstrip(",")
        if candidate in _CITY_REGION:
            return candidate, count
    for count in range(min(3, len(words)), 0, -1):
        candidate = " ".join(words[:count]).lower().rstrip(",")
        close = difflib.get_close_matches(candidate, _CITIES, n=1, cutoff=0.8)
        if close and len(candidate) > 3:
            return close[0], count
    return None


def _city_name(city: str) -> str:
    return _CITY_NAMES.get(city) or city.title()


def _split_city(text: str | None) -> tuple[str | None, str | None]:
    """(city, what follows it) from the text after a listing's last comma: "S.F. and 9:30pm" -> ("San Francisco",
    "and 9:30pm"). A city we don't know is kept as it is."""
    words = (text or "").split()
    if not words:
        return None, None
    known = _known_city(words)
    if not known:
        return text, None
    city, count = known
    return _city_name(city), " ".join(words[count:]) or None


def _venue_and_city(raw: RawShow) -> tuple[str, str | None, str | None]:
    """(venue name, city, leftover text). A listing without a comma before its city ("the Fox Theater Oakland")
    is split at a city we know."""
    if raw.city:
        name, _, last = raw.venue_name.rpartition(",")
        if name and not _known_city(raw.city.split()) and _known_city(last.split()):
            # More commas after the city: "the Castro, S.F. a/a $48 2:30pm/3pm, 5pm/5:30pm and 7:30pm/8pm shows".
            city, rest = _split_city(last)
            return name.strip(), city, "; ".join(p for p in (rest, raw.city) if p)
        city, rest = _split_city(raw.city)
        return raw.venue_name, city, rest
    words = raw.venue_name.split()
    for start in range(1, len(words)):
        known = _known_city(words[start:])
        if known and " ".join(words[start:start + known[1]]).lower() in _CITY_REGION:
            return " ".join(words[:start]), _city_name(known[0]), " ".join(words[start + known[1]:]) or None
    return raw.venue_name, None, None


def _show(raw: RawShow) -> dict:
    venue_name, city, rest = _venue_and_city(raw)
    notes = "; ".join(n for n in (raw.notes, rest) if n) or None
    door = _parse_time(raw.door_time)
    return {
        "date": raw.date,
        "bands": raw.bands,
        "act_notes": raw.act_notes,
        "band_enrichment": [(name, {"genres": []}) for name in raw.bands],
        "venue_name": venue_name,
        "city": city,
        "address": ", ".join(p for p in (raw.venue_address, city) if p) if raw.venue_address else None,
        "venue_website": None,
        "status": raw.status,
        "age_restriction": raw.age_restriction,
        "price_raw": raw.price_raw,
        "door_time": raw.door_time,
        "set_time": raw.set_time,
        "notes": notes,
        "is_recommended": raw.is_recommended,
        "will_sell_out": raw.will_sell_out,
        "is_pit": raw.is_pit,
        "is_drink_tickets": raw.is_drink_tickets,
        "is_no_reentry": raw.is_no_reentry,
        "is_sold_out": bool(notes and _SOLD_OUT_RE.search(notes)),
        "is_matinee": bool(door and door < _MATINEE_BEFORE),
        "is_benefit": bool(_BENEFIT_RE.search(" ".join(n for n in [notes, *raw.act_notes] if n))),
        "raw_text": raw.raw_text,
    }
