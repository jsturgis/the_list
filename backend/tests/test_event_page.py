"""An event page on any site (app/ingestion/event_page.py): TicketWeb's reader for TicketWeb, the page's schema.org
Event for any other site, and UnreadablePage (add a screenshot instead) when it can't be read."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import httpx
import pytest

from app.ingestion.event_page import UnreadablePage, fetch_event, site_name
from app.ingestion.ticketweb import EventError

_URL = "https://www.eventbrite.com/e/wet-leg-the-chapel-tickets-123?aff=ebdssbdestsearch"
_EVENT = {
    "@context": "https://schema.org", "@type": "MusicEvent", "name": "Wet Leg with Idles",
    "startDate": "2027-01-21T20:00:00-08:00", "url": "https://www.eventbrite.com/e/wet-leg-the-chapel-tickets-123",
    "location": {"@type": "Place", "name": "The Chapel",
                 "address": {"streetAddress": "777 Valencia St", "addressLocality": "San Francisco"}},
    "performer": [{"name": "Wet Leg"}, {"name": "Idles"}],
    "offers": [{"price": "25.00", "availability": "https://schema.org/InStock"}],
}


def _page(event: dict | None) -> str:
    ld = f'<script type="application/ld+json">{json.dumps(event)}</script>' if event else ""
    return f"<html><head>{ld}</head><body>An event</body></html>"


def _answer(status: int, text: str = "", url: str = _URL) -> httpx.Response:
    return httpx.Response(status, text=text, request=httpx.Request("GET", url))


@patch("app.ingestion.event_page.httpx.get")
def test_reads_any_sites_event_from_its_schema_org_event(get):
    get.return_value = _answer(200, _page(_EVENT))

    data = fetch_event(_URL)

    assert data["source"] == "page"
    assert data["bands"] == ["Wet Leg", "Idles"]
    assert (data["venue_name"], data["city"], data["date"]) == ("The Chapel", "San Francisco", date(2027, 1, 21))
    assert data["ticket_provider"] == "eventbrite.com"
    assert data["ticket_url"] == "https://www.eventbrite.com/e/wet-leg-the-chapel-tickets-123"
    assert data["price_raw"] == "$25"


@patch("app.ingestion.ticketweb.fetch_event", return_value={"source": "ticketweb"})
def test_reads_a_ticketweb_page_with_ticketwebs_reader(ticketweb):
    assert fetch_event("https://www.ticketweb.com/event/x/1")["source"] == "ticketweb"


@patch("app.ingestion.event_page.httpx.get")
def test_a_page_the_site_wont_serve_is_unreadable(get):
    get.return_value = _answer(530)
    with pytest.raises(UnreadablePage, match="couldn't fetch"):
        fetch_event(_URL)


@patch("app.ingestion.event_page.httpx.get")
def test_a_page_with_no_event_details_is_unreadable(get):
    get.return_value = _answer(200, _page(None))
    with pytest.raises(UnreadablePage, match="no event details"):
        fetch_event(_URL)


@patch("app.ingestion.event_page.httpx.get")
def test_an_event_outside_the_bay_area_isnt_unreadable_just_refused(get):
    """A screenshot wouldn't help: the event itself can't be added."""
    get.return_value = _answer(200, _page({**_EVENT, "location": {**_EVENT["location"],
                                                                     "address": {"addressLocality": "Portland"}}}))
    with pytest.raises(EventError, match="not a Bay Area city") as raised:
        fetch_event(_URL)
    assert not isinstance(raised.value, UnreadablePage)


def test_refuses_what_isnt_a_web_page():
    with pytest.raises(EventError, match="isn't a web page"):
        fetch_event("ftp://example.com/event")


def test_names_the_site():
    assert site_name("https://www.Eventbrite.com/e/1") == "eventbrite.com"
    assert site_name("https://thechapelsf.com/events/1") == "thechapelsf.com"
