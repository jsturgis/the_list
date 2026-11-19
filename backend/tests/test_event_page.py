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


# ── An event whose address names no city (Bandsintown's, with only the Venue's coordinates) ──────────────────

def _placed(venue: str, day: str, url_id: str, geo: tuple[float, float] | None) -> dict:
    """A tour date as Bandsintown's artist page gives it: the address's fields empty, the place's coordinates."""
    place = {"@type": "Place", "name": venue,
             "address": {"@type": "PostalAddress", "addressRegion": "", "streetAddress": "", "postalCode": ""}}
    if geo:
        place["geo"] = {"@type": "GeoCoordinates", "latitude": geo[0], "longitude": geo[1]}
    return _tour_date("", venue, day, url_id, location=place)


_FELTON, _CORNERSTONE, _PALO_ALTO = (37.05134, -122.0733), (37.8663201, -122.2673229), (37.4426, -122.1613)
# What Google Places has at the coordinates (google_places.city_at), for the tests.
_GOOGLE = {_FELTON: "Felton", _CORNERSTONE: "Berkeley", _PALO_ALTO: "Palo Alto"}


@pytest.fixture(autouse=True)
def google():
    """Google Places, asked where a place is: what _GOOGLE has there. Coordinates it hasn't fail the test."""
    with patch("app.ingestion.ticketweb.city_at", side_effect=lambda *at: _GOOGLE[at]) as city_at:
        yield city_at


_CURSIVE_TOUR = [
    _placed("Bluebird Theater", "2027-03-03", "1", (39.7403313, -104.9484849)),       # Denver
    _placed("Felton Music Hall", "2027-03-11", "2", _FELTON),
    _placed("Cornerstone Craft Beer & Live Music", "2027-03-13", "3", _CORNERSTONE),
    _placed("Tractor Tavern", "2027-03-08", "4", (47.665797, -122.3826794)),          # Seattle
]


@patch("app.ingestion.page_fetch.httpx.get")
def test_an_event_with_no_city_is_placed_by_its_coordinates(get, google):
    get.return_value = _answer(200, _artist_page(*_CURSIVE_TOUR), url=_ARTIST_URL)
    shows = fetch_events(_ARTIST_URL)
    assert [(s["venue_name"], s["city"]) for s in shows] == [
        ("Felton Music Hall", "Felton"), ("Cornerstone Craft Beer & Live Music", "Berkeley")]
    # Denver and Seattle are nowhere near the Bay: Google isn't asked about them.
    assert {c.args for c in google.call_args_list} == {_FELTON, _CORNERSTONE}


@patch("app.ingestion.page_fetch.httpx.get")
def test_an_event_in_a_town_google_names_but_the_list_doesnt_know_is_refused(get):
    """As it is when its address names the town: Palo Alto isn't taken for Stanford."""
    get.return_value = _answer(200, _page(_placed("The Guild", "2027-03-11", "2", _PALO_ALTO)), url=_URL)
    with pytest.raises(OutsideBayArea, match="The Guild is in Palo Alto"):
        fetch_events(_URL)


@patch("app.ingestion.page_fetch.httpx.get")
def test_when_google_cant_be_asked_the_event_isnt_refused_as_outside_the_bay_area(get, google):
    """It may be in the Bay Area: the admin is told why, to try again, not that it's elsewhere."""
    from app.ingestion.google_places import PlacesUnavailable

    google.side_effect = PlacesUnavailable("Google Places didn't answer: 503")
    get.return_value = _answer(200, _artist_page(*_CURSIVE_TOUR), url=_ARTIST_URL)
    with pytest.raises(EventError, match="couldn't tell where Felton Music Hall is: Google Places didn't answer") \
            as raised:
        fetch_events(_ARTIST_URL)
    assert not isinstance(raised.value, OutsideBayArea)


def _listed(venues: dict[str, str], at: dict[tuple[float, float], str] | None = None):
    """A `venue_city` for the List's Venues: their cities by name, and by coordinates."""
    return lambda name, coordinates=None: (at or {}).get(coordinates) if coordinates else venues.get(name)


@patch("app.ingestion.page_fetch.httpx.get")
def test_an_event_with_neither_city_nor_coordinates_takes_its_known_venues_city(get):
    get.return_value = _answer(200, _page(_placed("Felton Music Hall", "2027-03-11", "2", None)), url=_URL)
    (show,) = fetch_events(_URL, _listed({"Felton Music Hall": "Felton"}))
    assert show["city"] == "Felton"


@patch("app.ingestion.page_fetch.httpx.get")
def test_on_a_tour_a_known_venues_name_alone_doesnt_place_an_event(get):
    """An artist's tour plays many a Fillmore: only the one at the coordinates is the List's."""
    get.return_value = _answer(200, _artist_page(_placed("The Fillmore", "2027-03-11", "2", None),
                                                 _placed("Bluebird Theater", "2027-03-03", "1", None)),
                               url=_ARTIST_URL)
    with pytest.raises(OutsideBayArea, match="none of its 2 events"):
        fetch_events(_ARTIST_URL, _listed({"The Fillmore": "San Francisco"}))


@patch("app.ingestion.page_fetch.httpx.get")
def test_coordinates_outside_the_bay_area_win_over_a_known_venue_of_the_same_name(get):
    """Another city's "The Independent" isn't San Francisco's."""
    denver = _placed("The Independent", "2027-03-03", "1", (39.7403313, -104.9484849))
    get.return_value = _answer(200, _page(denver), url=_URL)
    with pytest.raises(OutsideBayArea):
        fetch_events(_URL, _listed({"The Independent": "San Francisco"}))


@patch("app.ingestion.page_fetch.httpx.get")
def test_a_known_venue_at_the_coordinates_gives_its_city_even_one_not_in_the_table(get):
    """The List's Sandbar, in Capitola: its city is taken without asking Google, and Capitola isn't refused."""
    sandbar = (36.9720, -121.9530)
    get.return_value = _answer(200, _artist_page(_placed("Sandbar", "2027-03-12", "5", sandbar), *_CURSIVE_TOUR[:2]),
                               url=_ARTIST_URL)
    shows = fetch_events(_ARTIST_URL, _listed({}, {sandbar: "Capitola"}))
    assert [(s["venue_name"], s["city"]) for s in shows] == [("Sandbar", "Capitola"), ("Felton Music Hall", "Felton")]


@patch("app.ingestion.page_fetch.httpx.get")
def test_an_event_with_empty_coordinates_is_read_as_one_with_none(get):
    blank = _placed("Felton Music Hall", "2027-03-11", "2", None)
    blank["location"]["geo"] = {"@type": "GeoCoordinates", "latitude": "", "longitude": None}
    get.return_value = _answer(200, _page(blank), url=_URL)
    (show,) = fetch_events(_URL, _listed({"Felton Music Hall": "Felton"}))
    assert show["city"] == "Felton"
