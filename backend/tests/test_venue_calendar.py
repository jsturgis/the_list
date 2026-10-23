"""Tests for match_calendar: matching a Venue's own scraped calendar entries against this run's Shows, and
working out what each Show still needs. Pure data in, data out -- no database, network or LLM.

The IO wrappers around it (finding the calendar page, reading it, and tying both to real Shows for one ingestion
run) are tested below with the network and LLM mocked, the same way tests/test_enrichment.py mocks
get_enrichment_llm and tests/test_band_photos.py mocks httpx.Client."""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from app.ingestion.venue_calendar import (
    CalendarEntry, CalendarUpdate, ShowLike, enrich_shows_from_venue_calendars, fetch_calendar_entries,
    find_calendar_url, match_calendar,
)
from app.ingestion.venue_corrections import CORRECTIONS, VenueCorrection

NIGHT = date(2026, 11, 14)


def _show(id=1, day=NIGHT, headliner="Redwood Sirens", has_flyer=False, has_more_info=False, has_ticket=False):
    return ShowLike(id=id, date=day, headliner=headliner, has_flyer=has_flyer, has_more_info=has_more_info,
                     has_ticket=has_ticket)


def test_a_show_alone_on_its_night_is_matched_by_date_and_gains_every_field():
    show = _show()
    entry = CalendarEntry(date=NIGHT, title="Redwood Sirens", flyer_url="https://venue.example/flyer.jpg",
                           more_info_url="https://venue.example/shows/1", ticket_url="https://tix.example/1")

    updates = match_calendar([show], [entry])

    assert updates == {
        1: CalendarUpdate(flyer_image_url="https://venue.example/flyer.jpg",
                          more_info_url="https://venue.example/shows/1", ticket_url="https://tix.example/1"),
    }


def test_an_entry_with_no_date_is_never_guessed_at():
    show = _show()
    entry = CalendarEntry(date=None, title="Redwood Sirens", flyer_url="https://venue.example/flyer.jpg")

    assert match_calendar([show], [entry]) == {}


def test_an_entry_whose_date_matches_no_show_is_ignored():
    show = _show()
    entry = CalendarEntry(date=date(2026, 12, 25), flyer_url="https://venue.example/flyer.jpg")

    assert match_calendar([show], [entry]) == {}


def test_fields_the_show_already_has_are_never_overwritten():
    """Steve's edition already gave this Show a ticket link; the calendar's different one is dropped."""
    show = _show(has_ticket=True)
    entry = CalendarEntry(date=NIGHT, flyer_url="https://venue.example/flyer.jpg",
                          ticket_url="https://other-tix.example/1")

    updates = match_calendar([show], [entry])

    assert updates == {1: CalendarUpdate(flyer_image_url="https://venue.example/flyer.jpg")}


def test_a_show_missing_only_one_field_gains_only_that_one():
    show = _show(has_flyer=True, has_ticket=True)
    entry = CalendarEntry(date=NIGHT, flyer_url="https://venue.example/flyer.jpg",
                          more_info_url="https://venue.example/shows/1", ticket_url="https://tix.example/1")

    updates = match_calendar([show], [entry])

    assert updates == {1: CalendarUpdate(more_info_url="https://venue.example/shows/1")}


def test_a_show_with_everything_already_gains_nothing_and_is_left_out_of_the_result():
    show = _show(has_flyer=True, has_more_info=True, has_ticket=True)
    entry = CalendarEntry(date=NIGHT, flyer_url="https://venue.example/flyer.jpg",
                          more_info_url="https://venue.example/shows/1", ticket_url="https://tix.example/1")

    assert match_calendar([show], [entry]) == {}


def test_an_early_and_late_show_the_same_night_are_disambiguated_by_headliner():
    early = _show(id=1, headliner="Redwood Sirens")
    late = _show(id=2, headliner="Night Owls")
    entries = [
        CalendarEntry(date=NIGHT, title="Night Owls", flyer_url="https://venue.example/owls.jpg"),
        CalendarEntry(date=NIGHT, title="Redwood Sirens", flyer_url="https://venue.example/sirens.jpg"),
    ]

    updates = match_calendar([early, late], entries)

    assert updates == {
        1: CalendarUpdate(flyer_image_url="https://venue.example/sirens.jpg"),
        2: CalendarUpdate(flyer_image_url="https://venue.example/owls.jpg"),
    }


def test_an_early_and_late_show_the_same_night_with_no_title_to_go_on_is_left_unmatched():
    early = _show(id=1, headliner="Redwood Sirens")
    late = _show(id=2, headliner="Night Owls")
    entry = CalendarEntry(date=NIGHT, title=None, flyer_url="https://venue.example/flyer.jpg")

    assert match_calendar([early, late], [entry]) == {}


def test_an_early_and_late_show_the_same_night_with_an_unrecognisable_title_is_left_unmatched():
    """A title that matches neither Show's headliner is never guessed at, not even as a 50/50 coin flip."""
    early = _show(id=1, headliner="Redwood Sirens")
    late = _show(id=2, headliner="Night Owls")
    entry = CalendarEntry(date=NIGHT, title="Some Other Band", flyer_url="https://venue.example/flyer.jpg")

    assert match_calendar([early, late], [entry]) == {}


def test_headliner_title_matching_tolerates_the_spelling_variations_band_key_already_does():
    """Same normalization as app.ingestion.upsert.band_key: case and punctuation don't count."""
    early = _show(id=1, headliner="B.F.H")
    late = _show(id=2, headliner="Night Owls")
    entry = CalendarEntry(date=NIGHT, title="b.f.h.", flyer_url="https://venue.example/flyer.jpg")

    assert match_calendar([early, late], [entry]) == {1: CalendarUpdate(flyer_image_url="https://venue.example/flyer.jpg")}


def _html_response(text: str) -> httpx.Response:
    """A 200 response with a request attached, so raise_for_status() behaves as it would through a real client."""
    return httpx.Response(200, text=text, request=httpx.Request("GET", "https://venue.example/"))


# ── find_calendar_url: ask the LLM for a candidate link, then verify it resolves ───────────────────────────────

@patch("app.ingestion.venue_calendar.httpx.head")
@patch("app.ingestion.venue_calendar.get_enrichment_llm")
@patch("app.ingestion.venue_calendar.httpx.get")
def test_find_calendar_url_returns_the_llms_candidate_once_it_resolves(mock_get, mock_llm, mock_head):
    mock_get.return_value = _html_response('<a href="/shows/">Shows</a> <a href="/contact">Contact</a>')
    llm_instance = MagicMock()
    llm_instance.with_structured_output.return_value.invoke.return_value = SimpleNamespace(url="/shows/")
    mock_llm.return_value = llm_instance
    mock_head.return_value = httpx.Response(200)

    assert find_calendar_url("Neck of the Woods", "https://venue.example/") == "https://venue.example/shows/"


@patch("app.ingestion.venue_calendar.httpx.head")
@patch("app.ingestion.venue_calendar.get_enrichment_llm")
@patch("app.ingestion.venue_calendar.httpx.get")
def test_find_calendar_url_is_none_when_the_candidate_doesnt_resolve(mock_get, mock_llm, mock_head):
    mock_get.return_value = _html_response('<a href="/shows/">Shows</a>')
    llm_instance = MagicMock()
    llm_instance.with_structured_output.return_value.invoke.return_value = SimpleNamespace(url="/shows/")
    mock_llm.return_value = llm_instance
    mock_head.return_value = httpx.Response(404)

    assert find_calendar_url("Neck of the Woods", "https://venue.example/") is None


@patch("app.ingestion.venue_calendar.get_enrichment_llm")
@patch("app.ingestion.venue_calendar.httpx.get")
def test_find_calendar_url_is_none_when_the_llm_finds_nothing_likely(mock_get, mock_llm):
    mock_get.return_value = _html_response('<a href="/contact">Contact</a>')
    llm_instance = MagicMock()
    llm_instance.with_structured_output.return_value.invoke.return_value = SimpleNamespace(url=None)
    mock_llm.return_value = llm_instance

    assert find_calendar_url("Neck of the Woods", "https://venue.example/") is None


@patch("app.ingestion.venue_calendar.httpx.get")
def test_find_calendar_url_is_none_when_the_homepage_cant_be_fetched(mock_get):
    mock_get.side_effect = httpx.ConnectError("unreachable")

    assert find_calendar_url("Neck of the Woods", "https://venue.example/") is None


# ── fetch_calendar_entries: ask the LLM to read the calendar page ──────────────────────────────────────────────

@patch("app.ingestion.venue_calendar.get_enrichment_llm")
@patch("app.ingestion.venue_calendar.httpx.get")
def test_fetch_calendar_entries_resolves_relative_urls_against_the_calendar_page(mock_get, mock_llm):
    mock_get.return_value = _html_response("<html>a calendar</html>")
    llm_instance = MagicMock()
    llm_instance.with_structured_output.return_value.invoke.return_value = SimpleNamespace(entries=[
        SimpleNamespace(date="2026-11-14", title="Redwood Sirens", flyer_url="/flyers/1.jpg",
                        more_info_url="/shows/1", ticket_url="https://tix.example/1"),
    ])
    mock_llm.return_value = llm_instance

    entries = fetch_calendar_entries("https://venue.example/shows/")

    assert entries == [CalendarEntry(date=date(2026, 11, 14), title="Redwood Sirens",
                                     flyer_url="https://venue.example/flyers/1.jpg",
                                     more_info_url="https://venue.example/shows/1",
                                     ticket_url="https://tix.example/1")]


@patch("app.ingestion.venue_calendar.get_enrichment_llm")
@patch("app.ingestion.venue_calendar.httpx.get")
def test_fetch_calendar_entries_with_an_unparseable_date_keeps_the_entry_undated(mock_get, mock_llm):
    mock_get.return_value = _html_response("<html>a calendar</html>")
    llm_instance = MagicMock()
    llm_instance.with_structured_output.return_value.invoke.return_value = SimpleNamespace(entries=[
        SimpleNamespace(date="sometime in November", title="Redwood Sirens", flyer_url=None,
                        more_info_url=None, ticket_url=None),
    ])
    mock_llm.return_value = llm_instance

    assert fetch_calendar_entries("https://venue.example/shows/") == [CalendarEntry(title="Redwood Sirens")]


@patch("app.ingestion.venue_calendar.httpx.get")
def test_fetch_calendar_entries_is_empty_when_the_page_cant_be_fetched(mock_get):
    mock_get.side_effect = httpx.ConnectError("unreachable")

    assert fetch_calendar_entries("https://venue.example/shows/") == []


@patch("app.ingestion.venue_calendar.get_enrichment_llm")
@patch("app.ingestion.venue_calendar.httpx.get")
def test_fetch_calendar_entries_is_empty_when_the_llm_fails(mock_get, mock_llm):
    mock_get.return_value = _html_response("<html>a calendar</html>")
    llm_instance = MagicMock()
    llm_instance.with_structured_output.return_value.invoke.side_effect = RuntimeError("down")
    mock_llm.return_value = llm_instance

    assert fetch_calendar_entries("https://venue.example/shows/") == []


# ── enrich_shows_from_venue_calendars: tying it together for one ingestion run ─────────────────────────────────

def _band(name):
    return SimpleNamespace(name=name)


def _act(name, position=0):
    return SimpleNamespace(position=position, band=_band(name))


def _venue(name="Neck of the Woods", website_url="https://venue.example/", calendar_url=None, calendar_checked_at=None):
    return SimpleNamespace(name=name, website_url=website_url, calendar_url=calendar_url,
                           calendar_checked_at=calendar_checked_at)


def _real_show(venue, id=1, day=NIGHT, headliner="Redwood Sirens", flyer_image_url=None, more_info_url=None,
               ticket_url=None):
    return SimpleNamespace(id=id, venue_id=1, venue=venue, date=day, acts=[_act(headliner)],
                           flyer_image_url=flyer_image_url, more_info_url=more_info_url, ticket_url=ticket_url)


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
@patch("app.ingestion.venue_calendar.find_calendar_url")
def test_a_correction_short_circuits_discovery_entirely(mock_find, mock_fetch):
    venue = _venue(name="Some Venue")
    show = _real_show(venue)
    CORRECTIONS["some-venue"] = VenueCorrection(calendar_url="https://corrected.example/shows/")
    mock_fetch.return_value = []
    try:
        enrich_shows_from_venue_calendars([show])
    finally:
        del CORRECTIONS["some-venue"]

    mock_find.assert_not_called()
    assert venue.calendar_url == "https://corrected.example/shows/"
    assert venue.calendar_checked_at is not None
    mock_fetch.assert_called_once_with("https://corrected.example/shows/")


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
@patch("app.ingestion.venue_calendar.find_calendar_url")
def test_a_venue_with_no_calendar_found_is_marked_checked_without_fetching(mock_find, mock_fetch):
    venue = _venue()
    show = _real_show(venue)
    mock_find.return_value = None

    assert enrich_shows_from_venue_calendars([show]) == 0

    assert venue.calendar_url is None
    assert venue.calendar_checked_at is not None
    mock_fetch.assert_not_called()


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
@patch("app.ingestion.venue_calendar.find_calendar_url")
def test_a_venue_already_checked_is_not_asked_again(mock_find, mock_fetch):
    venue = _venue(calendar_url="https://venue.example/shows/", calendar_checked_at=datetime(2026, 1, 1))
    show = _real_show(venue)
    mock_fetch.return_value = []

    enrich_shows_from_venue_calendars([show])

    mock_find.assert_not_called()


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
def test_a_venue_whose_current_shows_are_all_complete_is_never_fetched(mock_fetch):
    venue = _venue(calendar_url="https://venue.example/shows/", calendar_checked_at=datetime(2026, 1, 1))
    show = _real_show(venue, flyer_image_url="bands/1-a.webp", more_info_url="https://venue.example/shows/1",
                      ticket_url="https://tix.example/1")

    assert enrich_shows_from_venue_calendars([show]) == 0
    mock_fetch.assert_not_called()


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
def test_a_matched_entry_fills_the_real_shows_gaps(mock_fetch):
    venue = _venue(calendar_url="https://venue.example/shows/", calendar_checked_at=datetime(2026, 1, 1))
    show = _real_show(venue, ticket_url="https://steves-pick.example/1")  # the edition's own ticket link
    mock_fetch.return_value = [CalendarEntry(date=NIGHT, title="Redwood Sirens",
                                             flyer_url="https://venue.example/flyer.jpg",
                                             more_info_url="https://venue.example/shows/1",
                                             ticket_url="https://venue.example/tickets/1")]

    assert enrich_shows_from_venue_calendars([show]) == 1

    assert show.flyer_image_url == "https://venue.example/flyer.jpg"
    assert show.more_info_url == "https://venue.example/shows/1"
    assert show.ticket_url == "https://steves-pick.example/1"  # kept: never overwritten


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
def test_one_venues_failure_does_not_stop_the_others(mock_fetch):
    broken = _venue(name="Broken Venue", calendar_url="https://broken.example/", calendar_checked_at=datetime(2026, 1, 1))
    ok = _venue(name="OK Venue", calendar_url="https://ok.example/", calendar_checked_at=datetime(2026, 1, 1))
    broken_show = SimpleNamespace(id=1, venue_id=1, venue=broken, date=NIGHT, acts=[_act("Doomed")],
                                  flyer_image_url=None, more_info_url=None, ticket_url=None)
    ok_show = SimpleNamespace(id=2, venue_id=2, venue=ok, date=NIGHT, acts=[_act("Redwood Sirens")],
                              flyer_image_url=None, more_info_url=None, ticket_url=None)

    def fetch(url):
        if url == "https://broken.example/":
            raise RuntimeError("boom")
        return [CalendarEntry(date=NIGHT, title="Redwood Sirens", flyer_url="https://ok.example/flyer.jpg")]
    mock_fetch.side_effect = fetch

    assert enrich_shows_from_venue_calendars([broken_show, ok_show]) == 1
    assert ok_show.flyer_image_url == "https://ok.example/flyer.jpg"
    assert broken_show.flyer_image_url is None


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
def test_an_already_complete_early_show_does_not_steal_an_entry_meant_for_it_alone(mock_fetch):
    """Regression: match_calendar's same-night disambiguation needs every Show that night, not just the ones
    still missing something. If the already-complete "early" Show were left out of the candidate pool, the
    "late" Show (still missing its flyer) would look like the *only* candidate for this entry -- which is
    actually the early Show's -- and wrongly take its flyer."""
    venue = _venue(calendar_url="https://venue.example/shows/", calendar_checked_at=datetime(2026, 1, 1))
    early = _real_show(venue, id=1, headliner="Early Birds", flyer_image_url="shows/1-a.webp",
                       more_info_url="https://venue.example/shows/1", ticket_url="https://tix.example/1")
    late = _real_show(venue, id=2, headliner="Night Owls")  # still missing everything
    mock_fetch.return_value = [CalendarEntry(date=NIGHT, title="Early Birds", flyer_url="https://venue.example/early.jpg")]

    assert enrich_shows_from_venue_calendars([early, late]) == 0

    assert late.flyer_image_url is None                      # never mistaken for the early Show's entry
    assert early.flyer_image_url == "shows/1-a.webp"          # untouched: it already had one
