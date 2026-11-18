"""What an event page points to (app/ingestion/event_page.py, app/ingestion/bandsintown.py): a Bandsintown event's
whole lineup, each Show's own event page on an artist's page, and the ticket seller's page."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import pytest

from app.ingestion import bandsintown, ticketmaster
from app.ingestion.event_page import MAX_FOLLOWED, _merged, fetch_events, seller_url
from app.ingestion.page_fetch import PageError

_TICKETWEB_URL = "https://www.ticketweb.com/event/teenage-bottlerocket-w-brendan-kelly-moes-alley-tickets/14446334"
_TICKETWEB_PAGE = (Path(__file__).parent / "fixtures" / "ticketweb_event.html").read_text()
_EVENT_URL = "https://www.bandsintown.com/e/109163875-teenage-bottlerocket-at-moe's-alley"
_TM_URL = "https://www.ticketmaster.com/sunami-san-jose-california-12-26-2026/event/1C006550FA24DFD7"


def _affiliate(url: str) -> str:
    return f"https://ticketmaster.evyy.net/c/219208/271177/4272?u={quote(url, safe='')}&subId3=xid"


def _event(venue="Moe's Alley", city="Santa Cruz", day="2027-01-21", url=_EVENT_URL, **extra) -> dict:
    return {"@type": "MusicEvent", "name": f"Teenage Bottlerocket @ {venue}", "startDate": f"{day}T19:00:00",
            "url": f"{url}?came_from=209", "performer": {"@type": "MusicGroup", "name": "Teenage Bottlerocket"},
            "location": {"@type": "Place", "name": venue, "address": {"addressLocality": city}},
            "offers": {"@type": "Offer", "url": "https://www.bandsintown.com/t/109163875?came_from=209"}, **extra}


def _bandsintown_page(*events: dict, lineup=("Teenage Bottlerocket",), sellers=()) -> str:
    """A Bandsintown page as it's drawn: its JSON-LD, and its own data (window.__data) with the lineup and sellers."""
    ld = "".join(f'<script type="application/ld+json">{json.dumps(e)}</script>' for e in events)
    data = {"eventView": {"body": {
        "eventInfoContainer": {"lineupContainer": {"lineupItems": [{"id": n, "name": name}
                                                                   for n, name in enumerate(lineup)]}},
        "detailedTicketList": {"ticketList": [{"vendor": "x", "directTicketUrl": url} for url in sellers]}}}}
    return f"<html><head>{ld}</head><body><script>window.__data={json.dumps(data)}</script></body></html>"


def _site(pages: dict, waited: list | None = None):
    """get_page answering each URL from `pages`: its HTML, or a PageError for a page that can't be read. What each
    page was asked to wait for goes in `waited`."""
    def get_page(url, wait_for=None):
        if waited is not None:
            waited.append((url, wait_for))
        page = pages.get(url)
        if page is None or isinstance(page, Exception):
            raise page or PageError(f"404 from {url}")
        return page, url
    return get_page


# ── A Bandsintown event page ─────────────────────────────────────────────────

def test_reads_a_bandsintown_events_lineup_and_sellers_from_its_own_data():
    page = _bandsintown_page(_event(), lineup=["Sunami", "No Pressure (8pm)", "Midrift"],
                             sellers=[_affiliate(_TM_URL)])
    assert bandsintown.lineup(page) == ["Sunami", "No Pressure", "Midrift"]
    assert bandsintown.seller_urls(page) == [_affiliate(_TM_URL)]
    assert bandsintown.lineup("<html>no data</html>") == []


def test_a_bandsintown_events_whole_lineup_is_read_not_only_its_headliner():
    page = _bandsintown_page(_event(), lineup=["Teenage Bottlerocket", "Brendan Kelly", "Right to Remain"])
    with patch("app.ingestion.event_page.get_page", side_effect=_site({_EVENT_URL: page})):
        (show,) = fetch_events(_EVENT_URL)
    assert show["bands"] == ["Teenage Bottlerocket", "Brendan Kelly", "Right to Remain"]
    assert len(show["act_notes"]) == len(show["band_enrichment"]) == 3
    assert "offer_urls" not in show and "lineup_named" not in show   # the reader's own, not for ingest_shows


# ── The ticket seller's page ─────────────────────────────────────────────────

def test_the_sellers_page_adds_its_lineup_details_and_ticket_link():
    page = _bandsintown_page(_event(), sellers=[_affiliate(_TICKETWEB_URL)])
    pages = {_EVENT_URL: page, _TICKETWEB_URL: _TICKETWEB_PAGE}
    with patch("app.ingestion.event_page.get_page", side_effect=_site(pages)):
        (show,) = fetch_events(_EVENT_URL)

    assert show["bands"] == ["Teenage Bottlerocket", "Brendan Kelly"]
    assert (show["door_time"], show["set_time"]) == ("7pm", "8pm")   # the seller's doors and start, not the page's 7pm
    assert (show["price_raw"], show["age_restriction"]) == ("$20/$25", "21+")
    assert (show["ticket_provider"], show["ticket_url"]) == ("TicketWeb", _TICKETWEB_URL)
    assert show["source"] == "page"
    assert (show["venue_name"], show["date"]) == ("Moe's Alley", date(2027, 1, 21))


def test_a_seller_whose_page_cant_be_read_still_gives_its_ticket_link():
    """Ticketmaster's page fails (401 here): the Show keeps what it has, with Ticketmaster's link."""
    page = _bandsintown_page(_event(), lineup=["Teenage Bottlerocket", "Brendan Kelly"],
                             sellers=[_affiliate(_TM_URL + "?irgwc=1")])
    pages = {_EVENT_URL: page, _TM_URL + "?irgwc=1": PageError("401 from ticketmaster.com")}
    with patch("app.ingestion.event_page.get_page", side_effect=_site(pages)):
        (show,) = fetch_events(_EVENT_URL)
    assert (show["ticket_provider"], show["ticket_url"]) == ("ticketmaster.com", _TM_URL)   # unwrapped, untracked
    assert show["bands"] == ["Teenage Bottlerocket", "Brendan Kelly"]
    assert show["price_raw"] is None


def test_a_sellers_page_for_another_date_is_no_ticket_link():
    seller = _bandsintown_page(_event(day="2027-02-01", url="https://www.eventbrite.com/e/1"))
    page = _bandsintown_page(_event(), sellers=["https://www.eventbrite.com/e/1"])
    with patch("app.ingestion.event_page.get_page",
               side_effect=_site({_EVENT_URL: page, "https://www.eventbrite.com/e/1": seller})):
        (show,) = fetch_events(_EVENT_URL)
    assert (show["ticket_provider"], show["ticket_url"]) == ("bandsintown.com", _EVENT_URL)


def test_the_seller_has_the_last_word_on_sold_out_and_cancelled():
    seller = _bandsintown_page(_event(url="https://www.eventbrite.com/e/1", eventStatus="EventCancelled",
                                      offers={"availability": "https://schema.org/SoldOut"}))
    page = _bandsintown_page(_event(), sellers=["https://www.eventbrite.com/e/1"])
    with patch("app.ingestion.event_page.get_page",
               side_effect=_site({_EVENT_URL: page, "https://www.eventbrite.com/e/1": seller})):
        (show,) = fetch_events(_EVENT_URL)
    assert (show["status"], show["is_sold_out"]) == ("cancelled", True)


def test_a_sellers_event_name_that_isnt_a_lineup_adds_no_band():
    """Eventbrite's "TEENAGE BOTTLEROCKET Live in Berkeley", with no performers: the event's name, not a Band."""
    named = {"@type": "MusicEvent", "name": "TEENAGE BOTTLEROCKET Live in Berkeley", "startDate": "2027-01-21T19:00",
             "url": "https://www.eventbrite.com/e/1",
             "location": {"name": "Moe's Alley", "address": {"addressLocality": "Santa Cruz"}},
             "offers": {"price": "23.18"}}
    seller = f'<script type="application/ld+json">{json.dumps(named)}</script>'
    page = _bandsintown_page(_event(), sellers=["https://www.eventbrite.com/e/1"])
    with patch("app.ingestion.event_page.get_page",
               side_effect=_site({_EVENT_URL: page, "https://www.eventbrite.com/e/1": seller})):
        (show,) = fetch_events(_EVENT_URL)
    assert show["bands"] == ["Teenage Bottlerocket"]
    assert (show["price_raw"], show["ticket_provider"]) == ("$23.18", "eventbrite.com")


def test_bands_already_named_arent_added_again():
    assert _merged(["Teenage Bottlerocket"], ["TEENAGE BOTTLEROCKET", "teenage bottlerocket live", "Brendan Kelly"]) \
        == ["Teenage Bottlerocket", "Brendan Kelly"]
    assert _merged(["Ex"], ["Exhumed"]) == ["Ex", "Exhumed"]   # whole words only


def test_the_seller_is_the_first_ticket_link_on_another_site_unwrapped():
    show = {"ticket_url": _EVENT_URL, "offer_urls": ["https://www.bandsintown.com/t/1?came_from=209",
                                                     _affiliate(_TICKETWEB_URL), "https://www.eventbrite.com/e/2"]}
    assert seller_url(show) == _TICKETWEB_URL
    assert seller_url({"ticket_url": _EVENT_URL, "offer_urls": ["https://www.bandsintown.com/t/1"]}) is None


# ── An artist's page: each Show's own event page ─────────────────────────────

_ARTIST_URL = "https://www.bandsintown.com/a/9536-teenage-bottlerocket"


def test_each_bay_area_show_on_an_artists_page_reads_its_own_event_page_and_seller():
    moes, berkeley = _event(), _event("Berkeley Brewing Company", "Berkeley", "2027-01-24",
                                      "https://www.bandsintown.com/e/2-berkeley")
    pages = {
        _ARTIST_URL: _bandsintown_page(
            _event("Underworld", "London", "2026-11-23", "https://www.bandsintown.com/e/1"), moes, berkeley),
        _EVENT_URL: _bandsintown_page(moes, lineup=["Teenage Bottlerocket", "Brendan Kelly"],
                                      sellers=[_affiliate(_TICKETWEB_URL)]),
        _TICKETWEB_URL: _TICKETWEB_PAGE,
        "https://www.bandsintown.com/e/2-berkeley": PageError("403"),   # stays as the artist's page gave it
    }
    with patch("app.ingestion.event_page.get_page", side_effect=_site(pages)):
        shows = fetch_events(_ARTIST_URL)

    assert [(s["venue_name"], s["bands"], s["ticket_provider"]) for s in shows] == [
        ("Moe's Alley", ["Teenage Bottlerocket", "Brendan Kelly"], "TicketWeb"),
        ("Berkeley Brewing Company", ["Teenage Bottlerocket"], "bandsintown.com")]
    assert shows[0]["price_raw"] == "$20/$25"


def test_only_the_first_shows_on_an_artists_page_are_followed():
    days = [f"2027-03-{d:02d}" for d in range(1, MAX_FOLLOWED + 3)]
    events = [_event(day=day, url=f"https://www.bandsintown.com/e/{n}") for n, day in enumerate(days)]
    fetched = []

    def get_page(url):
        fetched.append(url)
        if url == _ARTIST_URL:
            return _bandsintown_page(*events), url
        raise PageError("403")
    with patch("app.ingestion.event_page.get_page", side_effect=get_page):
        shows = fetch_events(_ARTIST_URL)

    assert len(shows) == MAX_FOLLOWED + 2
    assert fetched == [_ARTIST_URL] + [f"https://www.bandsintown.com/e/{n}" for n in range(MAX_FOLLOWED)]


# ── Ticketmaster's price ─────────────────────────────────────────────────────

def _ticketmaster_page(*prices: str) -> str:
    """A Ticketmaster event page once drawn: its JSON-LD (no offers), and a ticket option for each price, as its
    markup has them (2026-11-18)."""
    event = {k: v for k, v in _event(url=_TM_URL, venue="San Jose Civic", city="San Jose", day="2026-12-26").items()
             if k != "offers"}
    options = "".join(f'<li role="menuitem" data-bdd="quick-picks-list-item-primary-{n}" tabindex="0" '
                      f'data-index="qp-{n}" data-price="{price}"><span data-bdd="quick-pick-price-button">{price}'
                      f'</span></li>' for n, price in enumerate(prices))
    return (f'<html><head><script type="application/ld+json">{json.dumps(event)}</script></head>'
            f'<body><ul>{options}</ul><div data-bdd="ticketBag-checkout">$0.00</div></body></html>')


def test_reads_the_price_from_the_ticket_options_ticketmaster_drew():
    assert ticketmaster.price(_ticketmaster_page("$48.00")) == "$48"
    assert ticketmaster.price(_ticketmaster_page("$65.50", "$48.00", "$1,250.00")) == "$48/$1250"
    assert ticketmaster.price(_ticketmaster_page()) is None   # sold out, or not on sale: no options


def test_a_ticketmaster_link_is_drawn_in_the_browser_and_gets_its_price():
    waited = []
    with patch("app.ingestion.event_page.get_page", side_effect=_site({_TM_URL: _ticketmaster_page("$48.00")},
                                                                       waited)):
        (show,) = fetch_events(_TM_URL)
    assert waited == [(_TM_URL, ticketmaster.READY)]
    assert (show["price_raw"], show["ticket_provider"]) == ("$48", "ticketmaster.com")


def test_ticketmaster_as_the_seller_gives_the_show_its_price():
    page = _bandsintown_page(_event(venue="San Jose Civic", city="San Jose", day="2026-12-26"),
                             sellers=[_affiliate(_TM_URL)])
    waited = []
    pages = {_EVENT_URL: page, _TM_URL: _ticketmaster_page("$48.00")}
    with patch("app.ingestion.event_page.get_page", side_effect=_site(pages, waited)):
        (show,) = fetch_events(_EVENT_URL)
    assert waited == [(_EVENT_URL, None), (_TM_URL, ticketmaster.READY)]
    assert (show["price_raw"], show["ticket_url"]) == ("$48", _TM_URL)
