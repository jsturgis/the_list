"""An event page on any site (app/ingestion/event_page.py): TicketWeb's reader for TicketWeb, the page's schema.org
Event for any other site, and UnreadablePage (add a screenshot instead) when it can't be read."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import httpx
import pytest

from app.ingestion.event_page import OutsideBayArea, UnreadablePage, fetch_events, site_name
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


@patch("app.ingestion.page_fetch.httpx.get")
def test_reads_any_sites_event_from_its_schema_org_event(get):
    get.return_value = _answer(200, _page(_EVENT))

    (data,) = fetch_events(_URL)

    assert data["source"] == "page"
    assert data["bands"] == ["Wet Leg", "Idles"]
    assert (data["venue_name"], data["city"], data["date"]) == ("The Chapel", "San Francisco", date(2027, 1, 21))
    assert data["ticket_provider"] == "eventbrite.com"
    assert data["ticket_url"] == "https://www.eventbrite.com/e/wet-leg-the-chapel-tickets-123"
    assert data["price_raw"] == "$25"


@patch("app.ingestion.ticketweb.fetch_event", return_value={"source": "ticketweb"})
def test_reads_a_ticketweb_page_with_ticketwebs_reader(ticketweb):
    assert fetch_events("https://www.ticketweb.com/event/x/1") == [{"source": "ticketweb"}]


@patch("app.ingestion.page_fetch.httpx.get")
def test_a_page_the_site_wont_serve_is_unreadable(get):
    get.return_value = _answer(530)
    with pytest.raises(UnreadablePage, match="couldn't fetch"):
        fetch_events(_URL)


@patch("app.ingestion.page_fetch.httpx.get")
def test_a_page_with_no_event_details_is_unreadable(get):
    get.return_value = _answer(200, _page(None))
    with pytest.raises(UnreadablePage, match="no event details"):
        fetch_events(_URL)


@patch("app.ingestion.page_fetch.httpx.get")
def test_an_event_outside_the_bay_area_isnt_unreadable_just_refused(get):
    """A screenshot wouldn't help: the event itself can't be added."""
    get.return_value = _answer(200, _page({**_EVENT, "location": {**_EVENT["location"],
                                                                     "address": {"addressLocality": "Portland"}}}))
    with pytest.raises(EventError, match="not a Bay Area city") as raised:
        fetch_events(_URL)
    assert not isinstance(raised.value, UnreadablePage)


def test_refuses_what_isnt_a_web_page():
    with pytest.raises(EventError, match="isn't a web page"):
        fetch_events("ftp://example.com/event")


def test_names_the_site():
    assert site_name("https://www.Eventbrite.com/e/1") == "eventbrite.com"
    assert site_name("https://thechapelsf.com/events/1") == "thechapelsf.com"


# ── A page listing several events (an artist's page) ─────────────────────────

_ARTIST_URL = "https://www.bandsintown.com/a/9536-teenage-bottlerocket?came_from=257"


def _tour_date(city: str, venue: str, day: str, url_id: str, **extra) -> dict:
    return {"@context": "https://schema.org", "@type": "MusicEvent", "name": f"Teenage Bottlerocket @ {venue}",
            "startDate": f"{day}T19:00:00", "url": f"https://www.bandsintown.com/e/{url_id}?came_from=209",
            "location": {"@type": "Place", "name": venue, "address": {"addressLocality": city}},
            "performer": [{"name": "Teenage Bottlerocket"}], **extra}


def _artist_page(*events: dict, doors: str = "") -> str:
    blocks = "".join(f'<script type="application/ld+json">{json.dumps(e)}</script>' for e in events)
    return f"<html><head>{blocks}</head><body>{doors}An artist</body></html>"


_TOUR = [
    _tour_date("London", "Underworld", "2026-11-23", "1"),
    _tour_date("Santa Cruz", "Moe's Alley", "2027-01-21", "2"),
    _tour_date("Portland", "Dante's", "2027-01-22", "3"),
    _tour_date("Berkeley", "Berkeley Brewing Company", "2027-01-24", "4"),
]


@patch("app.ingestion.page_fetch.httpx.get")
def test_an_artists_page_gives_its_bay_area_shows_and_passes_over_the_rest(get):
    get.return_value = _answer(200, _artist_page(*_TOUR), url=_ARTIST_URL)

    shows = fetch_events(_ARTIST_URL)

    assert [(s["venue_name"], s["city"], s["date"]) for s in shows] == [
        ("Moe's Alley", "Santa Cruz", date(2027, 1, 21)), ("Berkeley Brewing Company", "Berkeley", date(2027, 1, 24))]
    # Each Show's ticket link is its own event's page, not the artist's.
    assert [s["ticket_url"] for s in shows] == ["https://www.bandsintown.com/e/2", "https://www.bandsintown.com/e/4"]
    assert {s["ticket_provider"] for s in shows} == {"bandsintown.com"}
    assert all(s["bands"] == ["Teenage Bottlerocket"] for s in shows)


@patch("app.ingestion.page_fetch.httpx.get")
def test_an_artists_page_with_no_bay_area_show_is_refused(get):
    get.return_value = _answer(200, _artist_page(_TOUR[0], _TOUR[2]), url=_ARTIST_URL)
    with pytest.raises(OutsideBayArea, match="none of its 2 events is in a Bay Area city we know") as raised:
        fetch_events(_ARTIST_URL)
    assert not isinstance(raised.value, UnreadablePage)   # a screenshot wouldn't help


@patch("app.ingestion.page_fetch.httpx.get")
def test_a_bay_area_event_that_cant_be_read_is_passed_over_when_others_can_be(get):
    no_date = {k: v for k, v in _TOUR[3].items() if k != "startDate"}
    get.return_value = _answer(200, _artist_page(_TOUR[1], no_date, _TOUR[0]), url=_ARTIST_URL)
    assert [s["venue_name"] for s in fetch_events(_ARTIST_URL)] == ["Moe's Alley"]


@patch("app.ingestion.page_fetch.httpx.get")
def test_when_no_event_can_be_added_a_bay_area_ones_problem_is_given(get):
    """Not "none in the Bay Area" when one was, but couldn't be read."""
    no_date = {k: v for k, v in _TOUR[3].items() if k != "startDate"}
    get.return_value = _answer(200, _artist_page(no_date, _TOUR[0]), url=_ARTIST_URL)
    with pytest.raises(EventError, match="no start date"):
        fetch_events(_ARTIST_URL)


@patch("app.ingestion.page_fetch.httpx.get")
def test_the_pages_door_time_is_no_one_events_on_a_page_of_several(get):
    doors = '<div class="x">Doors open</div><div class="y">6:00 PM PST</div>'
    get.return_value = _answer(200, _artist_page(_TOUR[1], _TOUR[3], doors=doors), url=_ARTIST_URL)
    assert [s["door_time"] for s in fetch_events(_ARTIST_URL)] == ["7pm", "7pm"]   # each event's own start time
