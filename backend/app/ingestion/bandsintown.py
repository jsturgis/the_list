"""What a Bandsintown event page says beyond its schema.org Event (app/ingestion/event_page.py reads that).

Its JSON-LD names only the headliner as the performer. The page's own data (`window.__data`, which the page is drawn
from) has the whole lineup, and the ticket seller's own page: Bandsintown's ticket link (`/t/<event id>`) is a page of
its own that a script sends on, but the seller's link is there as `directTicketUrl`, inside an affiliate redirect.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from app.ingestion.parser import clean_band_name

_DATA_RE = re.compile(r"window\.__data\s*=\s*(\{.*?\})\s*;?\s*</script>", re.DOTALL)


def is_bandsintown_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == "bandsintown.com" or host.endswith(".bandsintown.com")


def _event_body(page: str) -> dict:
    match = _DATA_RE.search(page)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return {}
    body = (data.get("eventView") or {}).get("body") if isinstance(data, dict) else None
    return body if isinstance(body, dict) else {}


def lineup(page: str) -> list[str]:
    """The event's lineup as its page lists it ("Event lineup"), headliner first; empty when it isn't there."""
    items = (((_event_body(page).get("eventInfoContainer") or {}).get("lineupContainer") or {})
             .get("lineupItems") or [])
    names = [clean_band_name(str(item.get("name") or "")) for item in items if isinstance(item, dict)]
    return [name for name in names if name]


def seller_urls(page: str) -> list[str]:
    """The ticket sellers' links on the event's page (`directTicketUrl`), in the page's order."""
    tickets = ((_event_body(page).get("detailedTicketList") or {}).get("ticketList") or [])
    links = [t.get("directTicketUrl") for t in tickets if isinstance(t, dict)]
    return [link for link in links if isinstance(link, str) and link.startswith("http")]
