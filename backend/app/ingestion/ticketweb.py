"""An event page on TicketWeb (https://www.ticketweb.com/event/...), for a Show the List doesn't have yet.

`fetch_event` downloads the page; `event_show` maps it to a dict ready for `ingest_shows` (app/scheduler.py), shaped
as a listing from the List is (app/ingestion/steve_list.py), with `source` "ticketweb". The page's schema.org Event
(its JSON-LD) gives the lineup, start time, Venue, price and status; the door time is only in the page itself. The
price is the face value in the event's description, as Steve lists it; the JSON-LD's includes TicketWeb's fees.

A page can list several events (an artist's page on Bandsintown): `event_shows` reads each, keeping those in the Bay
Area and passing over the rest; only a page with none in the Bay Area is refused.

An event's city is its address's. Where the address has none (Bandsintown gives only the Venue's coordinates), it's
the city of the List's Venue at those coordinates, else, around the Bay, Google's city for the place there
(app/ingestion/google_places.py). With no coordinates either, it's the city of the List's Venue by that name, on a
page of one event only: an artist's tour plays many a Fillmore. The List's Venues are looked up by the caller
(`venue_city`, ingest_jobs.known_venue_city); a city one of them gives is taken as in the Bay Area, being on the List,
even when it isn't in the table (Capitola).

The page is fetched by app/ingestion/page_fetch.py: with a browser's headers, and from the home server's page fetcher
when there is one, since TicketWeb turns GitHub's runners away (ADR 0007).
"""
from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime, time
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from app.ingestion.page_fetch import PageError, get_page
from app.ingestion.parser import clean_band_name
from app.ingestion.google_places import PlacesUnavailable, city_at
from app.ingestion.upsert import around_the_bay, known_region

logger = logging.getLogger(__name__)

SOURCE = "ticketweb"
PROVIDER = "TicketWeb"

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

# The city of the List's Venue at the coordinates given, else (none given) by the name; None when the List has none.
VenueCity = Callable[[str, "tuple[float, float] | None"], "str | None"]


def no_venue_city(name: str, coordinates: tuple[float, float] | None = None) -> None:
    """For a caller with no Venues to look up: none is known."""
    return None


class EventError(RuntimeError):
    """The page couldn't be fetched, or isn't a TicketWeb event in the Bay Area."""


class OutsideBayArea(EventError):
    """The event is in a city that isn't one of the Bay Area's we know."""


class UnreadablePage(EventError):
    """The page couldn't be fetched (the site turned the request away), or has no event details on it: a
    screenshot of the event is the way to add it (app/ingestion/screenshot.py)."""


def is_ticketweb_url(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host == "ticketweb.com" or host.endswith(".ticketweb.com")


def event_url(url: str) -> str:
    """The event's page without the affiliate tracking a link from elsewhere carries (`?utm_medium=affiliate...`)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, "", ""))


def fetch_event(url: str, venue_city: VenueCity = no_venue_city) -> dict:
    """The Show on this TicketWeb event page."""
    if not is_ticketweb_url(url):
        raise EventError(f"{url} isn't a TicketWeb page")
    url = event_url(url)
    try:
        html, _ = get_page(url)
    except PageError as exc:
        raise UnreadablePage(f"couldn't fetch {url}: {exc}") from exc
    return event_show(html, url, venue_city=venue_city)


def _events(page: str) -> list[dict]:
    """The page's schema.org Events, in the page's order."""
    events = []
    for block in _LD_JSON_RE.findall(page):
        try:
            found = json.loads(block)
        except ValueError:
            continue
        for item in found if isinstance(found, list) else [found]:
            if isinstance(item, dict) and item.get("@type") in ("Event", "MusicEvent"):
                events.append(item)
    return events


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


def _has_performers(event: dict) -> bool:
    performers = event.get("performer") or event.get("performers") or []
    performers = [performers] if isinstance(performers, dict) else performers
    return any(isinstance(p, dict) and _text(p.get("name")) for p in performers)


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


def event_show(page: str, url: str, source: str = SOURCE, provider: str | None = PROVIDER,
               venue_city: VenueCity = no_venue_city) -> dict:
    """The Show on a TicketWeb event page (its HTML), as a dict for `ingest_shows`. Another site's page that
    describes its event the same way (schema.org JSON-LD) is read the same, with its own `source` and `provider`
    (app/ingestion/event_page.py)."""
    events = _events(page)
    if not events:
        raise _no_events(url)
    return _show(events[0], page, url, source, provider, venue_city)


def event_shows(page: str, url: str, source: str = SOURCE, provider: str | None = PROVIDER,
                venue_city: VenueCity = no_venue_city) -> list[dict]:
    """The Shows on a page that may list several events (an artist's page), as dicts for `ingest_shows`: those in the
    Bay Area, passing over the rest. A page with one event is read as `event_show` reads it. With several, an event
    that can't be read is passed over too (logged), and the page is refused only when none of them can be added."""
    events = _events(page)
    if not events:
        raise _no_events(url)
    if len(events) == 1:
        return [_show(events[0], page, url, source, provider, venue_city)]
    shows, outside, problems = [], 0, []
    # A Venue the List has by the name of one of several events' isn't taken for where it is: only by its coordinates.
    by_coordinates = lambda name, coordinates=None: venue_city(name, coordinates) if coordinates else None
    for event in events:
        try:
            # The page's own text belongs to no one event, so only the events' own details are read.
            shows.append(_show(event, None, url, source, provider, by_coordinates))
        except OutsideBayArea:
            outside += 1
        except EventError as exc:
            logger.info("%s: passing over an event: %s", url, exc)
            problems.append(exc)
    if shows:
        return shows
    if problems:
        raise problems[0]
    raise OutsideBayArea(f"{url}: none of its {outside} events is in a Bay Area city we know")


def _city(place: dict, venue_name: str, venue_city: VenueCity) -> tuple[str | None, bool]:
    """The city of a place whose address doesn't name one, and whether it's a Venue the List has: the List's Venue at
    its coordinates, else Google's city for the place there; with no coordinates, the List's Venue by its name. A place
    whose coordinates aren't in the Bay Area isn't taken for a Venue of the same name that is. Raises
    PlacesUnavailable when it takes Google to say, and Google can't be asked."""
    geo = place.get("geo") if isinstance(place.get("geo"), dict) else {}
    try:
        coordinates = (float(geo["latitude"]), float(geo["longitude"]))
    except (KeyError, TypeError, ValueError):
        coordinates = None
    if listed := venue_city(venue_name, coordinates):
        return listed, True
    if coordinates and around_the_bay(*coordinates):
        return city_at(*coordinates), False
    return None, False


def _no_events(url: str) -> UnreadablePage:
    return UnreadablePage(f"{url} has no event details on it (the site may have turned the request away)")


def _show(event: dict, page: str | None, url: str, source: str, provider: str | None,
          venue_city: VenueCity = no_venue_city) -> dict:
    """One event as a Show; `page` is the page's HTML when the event is the page's only one (its door time)."""
    url = event_url(event.get("url") or url)
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
    if not venue_name:
        raise EventError(f"{url}: no venue")
    city, listed = _text(address.get("addressLocality")) or None, False
    if not city:
        try:
            city, listed = _city(place, venue_name, venue_city)
        except PlacesUnavailable as exc:
            raise EventError(f"{url}: couldn't tell where {venue_name} is: {exc}") from exc
    if known_region(city) is None and not listed:
        raise OutsideBayArea(f"{url}: {venue_name} is in {city or 'an unknown city'}, not a Bay Area city we know")
    street = _text(address.get("streetAddress")) or None

    description = _text(event.get("description"))
    doors = (page and _DOORS_RE.search(page)) or _DESCRIPTION_DOORS_RE.search(description)
    door = _parse_clock(doors.group(1)) if doors else None
    shown = start.time() if (start.hour, start.minute) != (0, 0) else None   # a date with no time isn't midnight
    age = _AGE_RE.search(description)
    offers = _offers(event)
    status = str(event.get("eventStatus") or "").rsplit("/", 1)[-1]
    website = place.get("sameAs")

    return {
        "source": source,
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
        "ticket_provider": provider,
        "ticket_url": url,
        # Where the event's tickets are sold, as the page links them (app/ingestion/event_page.py follows one).
        "offer_urls": [o["url"] for o in offers if isinstance(o.get("url"), str) and o["url"].startswith("http")],
        # Whether the lineup is one: named as performers, or a name that split into several. An event's name that
        # didn't split ("Teenage Bottlerocket Live in Berkeley") is no lineup to add to another's.
        "lineup_named": _has_performers(event) or len(bands) > 1,
        "raw_text": f"{title} at {venue_name}" + (f", {city}" if city else ""),
    }
