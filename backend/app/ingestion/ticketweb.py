"""An event page on TicketWeb (https://www.ticketweb.com/event/...), for a Show the List doesn't have yet.

`fetch_event` downloads the page; `event_show` maps it to a dict ready for `ingest_shows` (app/scheduler.py), shaped
as a listing from the List is (app/ingestion/steve_list.py), with `source` "ticketweb". The page's schema.org Event
(its JSON-LD) gives the lineup, start time, Venue, price and status; the door time is only in the page itself. The
price is the face value in the event's description, as Steve lists it; the JSON-LD's includes TicketWeb's fees.

TicketWeb turns away requests that don't look like a browser ("Your browsing activity has been paused"), so the
page is asked for with a browser's headers.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, time
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.ingestion.parser import clean_band_name
from app.ingestion.upsert import known_region

SOURCE = "ticketweb"
PROVIDER = "TicketWeb"

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
_LD_JSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
# "<div ...>Doors open</div><div ...>7:00 PM PST</div>"
_DOORS_RE = re.compile(r">\s*Doors open\s*</div>\s*<div[^>]*>\s*(\d{1,2}(?::\d{2})?\s*[AP]M)", re.IGNORECASE)
# ... else the description's "Doors: 7pm // Show: 8pm"
_DESCRIPTION_DOORS_RE = re.compile(r"\bdoors\s*(?:open|at)?\s*:?\s*(\d{1,2}(?::\d{2})?\s*[ap]\.?m)", re.IGNORECASE)
_AGE_RE = re.compile(r"(?<![\w$])(\d{1,2}\+|all ages|a/a)(?!\w)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
# A dollar amount in the description; the first short line with one is its price line, not a paragraph of prose.
_AMOUNT_RE = re.compile(r"\$(\d+(?:\.\d{2})?)(?![\d,])")   # not "$10,000"
_PRICE_LINE_MAX = 80
# The event's name, as its JSON-LD gives it: "Tickets for <lineup> | TicketWeb - <venue> in <city>, US".
_TITLE_RE = re.compile(r"^(?:Tickets for\s+)?(.*?)(?:\s+\|\s+TicketWeb\b.*)?$")
_LINEUP_SEPARATORS_RE = re.compile(r"\s+(?:w/|with|and special guests?|special guests?)\s+|\s*,\s*|\s+\+\s+",
                                   re.IGNORECASE)
_MATINEE_BEFORE = time(17, 0)
_STATUSES = {"EventCancelled": "cancelled", "EventPostponed": "postponed"}


class EventError(RuntimeError):
    """The page couldn't be fetched, or isn't a TicketWeb event in the Bay Area."""


def is_ticketweb_url(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host == "ticketweb.com" or host.endswith(".ticketweb.com")


def event_url(url: str) -> str:
    """The event's page without the affiliate tracking a link from elsewhere carries (`?utm_medium=affiliate...`)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, "", ""))


def fetch_event(url: str) -> dict:
    """The Show on this TicketWeb event page."""
    if not is_ticketweb_url(url):
        raise EventError(f"{url} isn't a TicketWeb page")
    url = event_url(url)
    try:
        response = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EventError(f"couldn't fetch {url}: {exc}") from exc
    return event_show(response.text, url)


def _event(page: str) -> dict | None:
    for block in _LD_JSON_RE.findall(page):
        try:
            found = json.loads(block)
        except ValueError:
            continue
        for item in found if isinstance(found, list) else [found]:
            if isinstance(item, dict) and item.get("@type") in ("Event", "MusicEvent"):
                return item
    return None


def _text(value) -> str:
    """Plain text from a JSON-LD string, which TicketWeb leaves HTML-escaped and with <br /> tags."""
    return html.unescape(_TAG_RE.sub("\n", value or "")).strip()


def _clock(t: time) -> str:
    """A time as the List writes it, which `upsert_shows` reads: "8pm", "7:30pm"."""
    hour = t.hour % 12 or 12
    suffix = "am" if t.hour < 12 else "pm"
    return f"{hour}{suffix}" if t.minute == 0 else f"{hour}:{t.minute:02d}{suffix}"


def _parse_clock(text: str) -> time | None:
    text = re.sub(r"[\s.]", "", text).upper()
    for fmt in ("%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _title(event: dict) -> str:
    return _TITLE_RE.match(_text(event.get("name"))).group(1).strip()


def _bands(event: dict, title: str) -> list[str]:
    performers = event.get("performer") or event.get("performers") or []
    if isinstance(performers, dict):
        performers = [performers]
    names = [_text(p.get("name")) for p in performers if isinstance(p, dict)]
    if not any(names):
        names = _LINEUP_SEPARATORS_RE.split(title)   # no performers given: the lineup in the event's name
    seen: set[str] = set()
    bands = []
    for name in (clean_band_name(n) for n in names if n):
        if name and name.lower() not in seen:
            seen.add(name.lower())
            bands.append(name)
    return bands


def _offers(event: dict) -> list[dict]:
    offers = event.get("offers") or []
    return [o for o in (offers if isinstance(offers, list) else [offers]) if isinstance(o, dict)]


def _price(description: str, offers: list[dict]) -> str | None:
    """The price as the List writes it ("$25", "$20/$25"), which `upsert_shows` reads: the face value from the
    description's price line ("$20 in advance // $25 day of the show"), else the offers' (with TicketWeb's fees)."""
    for line in description.splitlines():
        if len(line) <= _PRICE_LINE_MAX and (face := _AMOUNT_RE.findall(line)):
            amounts = [float(a) for a in face]
            return _money_range(min(amounts), max(amounts))
    amounts = []
    for offer in offers:
        for key in ("price", "lowPrice", "highPrice"):
            try:
                amounts.append(float(offer[key]))
            except (KeyError, TypeError, ValueError):
                continue
    if not amounts:
        return None
    return _money_range(min(amounts), max(amounts))


def _money_range(low: float, high: float) -> str:
    if high == 0:
        return "free"
    money = lambda a: f"${a:g}" if a == int(a) else f"${a:.2f}"
    return money(low) if low == high else f"{money(low)}/{money(high)}"


def event_show(page: str, url: str) -> dict:
    """The Show on a TicketWeb event page (its HTML), as a dict for `ingest_shows`."""
    event = _event(page)
    if event is None:
        raise EventError(f"{url} has no event on it (TicketWeb may have turned the request away)")
    title = _title(event)
    bands = _bands(event, title)
    if not bands:
        raise EventError(f"{url}: no lineup in {title!r}")
    try:
        start = datetime.fromisoformat(event["startDate"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EventError(f"{url}: no start date") from exc

    place = event.get("location") or {}
    address = place.get("address") or {}
    venue_name = _text(place.get("name"))
    city = _text(address.get("addressLocality")) or None
    if not venue_name:
        raise EventError(f"{url}: no venue")
    if known_region(city) is None:
        raise EventError(f"{url}: {venue_name} is in {city or 'an unknown city'}, not a Bay Area city we know")
    street = _text(address.get("streetAddress")) or None

    description = _text(event.get("description"))
    doors = _DOORS_RE.search(page) or _DESCRIPTION_DOORS_RE.search(description)
    door = _parse_clock(doors.group(1)) if doors else None
    shown = start.time() if (start.hour, start.minute) != (0, 0) else None   # a date with no time isn't midnight
    age = _AGE_RE.search(description)
    offers = _offers(event)
    status = str(event.get("eventStatus") or "").rsplit("/", 1)[-1]
    website = place.get("sameAs")

    return {
        "source": SOURCE,
        "date": start.date(),
        "bands": bands,
        "act_notes": [None] * len(bands),
        "band_enrichment": [(name, {"genres": []}) for name in bands],
        "venue_name": venue_name,
        "city": city,
        "address": ", ".join(p for p in (street, city) if p) if street else None,
        "venue_website": website if isinstance(website, str) and website.startswith("http") else None,
        "status": _STATUSES.get(status, "upcoming"),
        "age_restriction": {"all ages": "a/a"}.get(age.group(1).lower(), age.group(1)) if age else None,
        "price_raw": _price(description, offers),
        # With no door time on the page, the start time is the Show's time, as for a listing with one time.
        "door_time": _clock(door) if door else (_clock(shown) if shown else None),
        "set_time": _clock(shown) if door and shown else None,
        "notes": None,
        "is_recommended": False,
        "will_sell_out": False,
        "is_pit": False,
        "is_drink_tickets": False,
        "is_no_reentry": False,
        "is_sold_out": any(str(o.get("availability", "")).endswith("SoldOut") for o in offers),
        "is_matinee": bool((door or shown) and (door or shown) < _MATINEE_BEFORE),
        "is_benefit": False,
        "ticket_provider": PROVIDER,
        "ticket_url": event_url(event.get("url") or url),
        "raw_text": f"{title} at {venue_name}" + (f", {city}" if city else ""),
    }
