"""Import a formatted edition of Steve's list (schema v2.0.0): structured JSON, one entry per Show.

Each event carries a status, a per-Show age restriction, Steve's flag symbols (`list_flags`),
structured times and ticketing, its Venue (name, address, url, coordinates, region) and its Bands
(name, role, genre, url, optional note), plus `raw_details`: the email's own notation
("16+ $58.15 7pm/8pm #"). Output dicts are ready for `upsert_shows`.

Door and set times are taken from `raw_details` first, parsed the way the email parser always has
(a lone time is the door time), because door time is part of a Show's identity; the structured
`doors_time`/`show_time` only fill gaps.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from urllib.parse import urlparse

from app.ingestion.parser import _parse_venue_part

# The flag legend ("* All bands deserve 3 stars ...") and everything after it isn't Show data; the
# producer sometimes appends it to the last event's details.
_LEGEND_RE = re.compile(r"\s*\*?\s*All bands deserve.*$", re.IGNORECASE | re.DOTALL)
_GENRE_SPLIT_RE = re.compile(r"\s*[/,]\s*")

_STATUS = {"scheduled": "upcoming", "cancelled": "cancelled", "postponed": "postponed"}
_AGE = {"all_ages": "a/a", "unspecified": None}
# Steve's legend: * All bands deserve 3 stars, $ will probably sell out, @ mosh pit warning,
# ^ under 21 must pay more, # no ins/outs.
_FLAG_FIELDS = {"*": "is_recommended", "$": "will_sell_out", "@": "is_pit", "^": "is_drink_tickets",
                "#": "is_no_reentry"}
# Used when a Venue address has no city part.
_REGION_CITY = {"San Francisco Venues": "San Francisco"}
# The producer's placeholder when it couldn't split a listing; never a real address.
_PLACEHOLDER_ADDRESS = "san francisco bay area"


def edition_meta(doc: dict) -> dict:
    """Subject line (title and edition date) and edition date, recorded on the ingestion run."""
    edition_date = date.fromisoformat(doc["edition_date"])
    return {
        "subject": f"{doc['title']} — {edition_date.strftime('%b')} {edition_date.day}, {edition_date.year}",
        "edition_date": edition_date,
    }


def edition_shows(doc: dict) -> list[dict]:
    """One upsert-ready dict per event in the edition."""
    return [_show(event) for event in doc.get("events", [])]


def _show(event: dict) -> dict:
    details = _LEGEND_RE.sub("", event.get("raw_details") or "").strip()
    parsed = _parse_venue_part(details)  # age, price, times, flags, "(...)" notes; leftovers as name/city
    leftovers = " ".join(p for p in (parsed["venue_name"], parsed["city"]) if p)

    artists = [a for a in event.get("artists", []) if (a.get("name") or "").strip()]
    artists.sort(key=lambda a: a.get("role") != "headliner")  # stable: headliner first, order kept
    venue_name, city, address, listing = _venue(event)
    venue = event.get("venue") or {}
    coordinates = venue.get("coordinates") or {}

    notes = [n for n in (parsed["notes"], leftovers, listing.get("notes")) if n]
    notes += [f"{a['name'].strip()}: {a['note'].strip()}" for a in artists if (a.get("note") or "").strip()]

    age = event.get("age_restriction")
    show = {
        "date": datetime.strptime(event["date"], "%b %d, %Y").date(),
        "bands": [a["name"].strip() for a in artists],
        "band_enrichment": [(a["name"].strip(), _band_enrichment(a)) for a in artists],
        "venue_name": venue_name,
        "city": city or _REGION_CITY.get(venue.get("region", "")),
        "address": address,
        "venue_website": (venue.get("url") or "").strip() or None,
        "latitude": coordinates.get("lat"),
        "longitude": coordinates.get("lng"),
        "status": _STATUS.get((event.get("status") or "").lower(), "upcoming"),
        "age_restriction": _AGE.get(age, age) or parsed["age_restriction"] or listing.get("age_restriction"),
        "price_raw": parsed["price_raw"] or listing.get("price_raw") or _ticket_price(event.get("ticketing") or {}),
        "door_time": parsed["door_time"] or listing.get("door_time") or _clock(event.get("doors_time")),
        "set_time": parsed["set_time"] or listing.get("set_time")
                    or (_clock(event.get("show_time")) if not parsed["door_time"] else None),
        "notes": "; ".join(notes) or None,
        "raw_text": json.dumps({**event, "raw_details": details}, ensure_ascii=False),
    }
    symbols = set(event.get("list_flags") or [])
    for symbol, field in _FLAG_FIELDS.items():
        show[field] = symbol in symbols or bool(parsed[field] or listing.get(field))
    return show


def _venue(event: dict) -> tuple[str | None, str | None, str | None, dict]:
    """(venue name, city, street address, fields parsed from an unsplit listing)."""
    venue = event.get("venue") or {}
    name = (venue.get("name") or "").strip()
    address = (venue.get("address") or "").strip()
    if address.lower() == _PLACEHOLDER_ADDRESS:
        address = ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if len(parts) >= 2:
        return name or None, parts[-1], address, {}
    if len(parts) == 1:  # just a city
        return name or None, parts[0], None, {}
    if "," in name:
        # The producer left the whole listing in the name ("Gray Area, S.F. 21+ $30 8pm"): parse it
        # the way the email parser parses the text after " at ".
        listing = _parse_venue_part(name)
        street = listing.get("venue_address")
        street_address = ", ".join(p for p in (street, listing["city"]) if p) if street else None
        return listing["venue_name"], listing["city"], street_address, listing
    return name or None, None, None, {}


def _clock(hhmm: str | None) -> str | None:
    """"19:30" -> "7:30pm", in the notation the rest of the pipeline parses."""
    if not hhmm:
        return None
    t = datetime.strptime(hhmm, "%H:%M")
    hour = t.hour % 12 or 12
    return f"{hour}{t.strftime(':%M') if t.minute else ''}{'am' if t.hour < 12 else 'pm'}"


def _ticket_price(ticketing: dict) -> str | None:
    if ticketing.get("is_free"):
        return "free"
    prices = [p for p in (ticketing.get("price_advance"), ticketing.get("price_door")) if p is not None]
    if not prices:
        return None
    fmt = lambda p: f"${p:g}" if p == int(p) else f"${p:.2f}"
    return "/".join(dict.fromkeys(fmt(p) for p in prices))


def _band_enrichment(artist: dict) -> dict:
    genres = [g.lower() for g in _GENRE_SPLIT_RE.split((artist.get("genre") or "").strip()) if g]
    url = (artist.get("url") or "").strip()
    host = urlparse(url).netloc.lower()
    return {
        "genres": list(dict.fromkeys(genres)),
        "spotify_url": url if host.endswith("spotify.com") else None,
        "soundcloud_url": url if host.endswith("soundcloud.com") else None,
        "bandcamp_url": url if host.endswith("bandcamp.com") else None,
    }
