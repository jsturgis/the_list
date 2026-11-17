"""Tests for match_calendar: matching a Venue's own scraped calendar entries against this run's Shows, and
working out what each Show still needs. Pure data in, data out -- no database, network or LLM.

The IO wrappers around it (finding the calendar page, reading it, and tying both to real Shows for one ingestion
run) are tested below with the network and LLM mocked, the same way tests/test_enrichment.py mocks
get_enrichment_llm and tests/test_band_photos.py mocks httpx.Client."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.ingestion.venue_calendar import (
    CalendarEntry, CalendarGone, CalendarUpdate, LookupFailed, ShowLike, _clean_html,
    enrich_shows_from_venue_calendars, fetch_calendar_entries, find_calendar_url, match_calendar,
)
from app.ingestion.venue_corrections import CORRECTIONS, VenueCorrection

NIGHT = date(2026, 11, 14)


@pytest.fixture(autouse=True)
def _llm_key(monkeypatch):
    """The calendar step is skipped without an LLM key (CI has none); these tests stand the LLM in themselves."""
    from app.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")


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


def test_a_show_alone_on_its_night_takes_the_entry_with_its_headliner_not_the_last_one_that_night():
    """A second room or a late DJ night: the calendar lists more than the one Show Steve has."""
    show = _show(headliner="Deafheaven")
    ours = CalendarEntry(date=NIGHT, title="Deafheaven", flyer_url="https://venue.example/a.jpg",
                         more_info_url="https://venue.example/a")
    other = CalendarEntry(date=NIGHT, title="Late Night DJ Party", flyer_url="https://venue.example/b.jpg",
                          more_info_url="https://venue.example/b")

    assert match_calendar([show], [ours, other]) == match_calendar([show], [other, ours]) == {
        1: CalendarUpdate(flyer_image_url="https://venue.example/a.jpg", more_info_url="https://venue.example/a"),
    }


def test_a_show_alone_on_its_night_with_several_entries_none_its_headliner_is_left_unmatched():
    show = _show(headliner="Deafheaven")
    entries = [CalendarEntry(date=NIGHT, title="Comedy Night", flyer_url="https://venue.example/a.jpg"),
               CalendarEntry(date=NIGHT, title="Late Night DJ Party", flyer_url="https://venue.example/b.jpg")]

    assert match_calendar([show], entries) == {}


def test_a_show_two_entries_both_claim_is_left_unmatched():
    show = _show(headliner="Deafheaven")
    entries = [CalendarEntry(date=NIGHT, title="Deafheaven", flyer_url="https://venue.example/a.jpg"),
               CalendarEntry(date=NIGHT, title="Deafheaven", flyer_url="https://venue.example/b.jpg")]

    assert match_calendar([show], entries) == {}


def test_a_show_alone_with_one_untitled_entry_that_night_still_matches_by_date():
    show = _show()
    entry = CalendarEntry(date=NIGHT, title=None, flyer_url="https://venue.example/flyer.jpg")

    assert match_calendar([show], [entry]) == {1: CalendarUpdate(flyer_image_url="https://venue.example/flyer.jpg")}


def test_a_title_that_holds_the_headliner_among_other_words_matches_it():
    """Calendars dress titles up: "Deafheaven w/ Special Guests", "Deafheaven / Touché Amoré"."""
    early = _show(id=1, headliner="Deafheaven")
    late = _show(id=2, headliner="Night Owls")
    entry = CalendarEntry(date=NIGHT, title="Deafheaven w/ Special Guests", flyer_url="https://venue.example/a.jpg")

    assert match_calendar([early, late], [entry]) == {1: CalendarUpdate(flyer_image_url="https://venue.example/a.jpg")}


def test_a_title_naming_another_act_on_the_bill_matches_that_show():
    early = ShowLike(id=1, date=NIGHT, headliner="Touché Amoré", has_flyer=False, has_more_info=False,
                     has_ticket=False, acts=("Touché Amoré", "Deafheaven"))
    late = _show(id=2, headliner="Night Owls")
    entry = CalendarEntry(date=NIGHT, title="Deafheaven (co-headline)", flyer_url="https://venue.example/a.jpg")

    assert match_calendar([early, late], [entry]) == {1: CalendarUpdate(flyer_image_url="https://venue.example/a.jpg")}


def test_a_name_only_matches_as_whole_words():
    """"X" isn't in "Xiu Xiu"'s title as a name, only as letters."""
    early = _show(id=1, headliner="X")
    late = _show(id=2, headliner="Night Owls")
    entry = CalendarEntry(date=NIGHT, title="Xiu Xiu", flyer_url="https://venue.example/a.jpg")

    assert match_calendar([early, late], [entry]) == {}


def test_a_title_naming_both_shows_headliners_is_left_unmatched():
    early = _show(id=1, headliner="Deafheaven")
    late = _show(id=2, headliner="Night Owls")
    entry = CalendarEntry(date=NIGHT, title="Deafheaven + Night Owls", flyer_url="https://venue.example/a.jpg")

    assert match_calendar([early, late], [entry]) == {}


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


def _html_response(text: str, status: int = 200, url: str = "https://venue.example/") -> httpx.Response:
    """A response with a request attached, as a real client returns it (resp.url is the page's address)."""
    return httpx.Response(status, text=text, request=httpx.Request("GET", url))


def _llm(answer=None, error=None):
    """A stand-in for get_enrichment_llm: its structured-output call answers `answer` or raises `error`."""
    instance = MagicMock()
    invoke = instance.with_structured_output.return_value.invoke
    if error:
        invoke.side_effect = error
    else:
        invoke.return_value = answer
    return MagicMock(return_value=instance)


# ── find_calendar_url: ask the LLM for a candidate link, then verify it resolves ───────────────────────────────

_HOMEPAGE = _html_response('<a href="/shows/">Shows</a> <a href="/contact">Contact</a>')


@patch("app.ingestion.venue_calendar._head", return_value=httpx.Response(200))
@patch("app.ingestion.venue_calendar._get", return_value=_HOMEPAGE)
def test_find_calendar_url_returns_the_llms_candidate_once_it_resolves(mock_get, mock_head):
    with patch("app.ingestion.venue_calendar.get_enrichment_llm", _llm(SimpleNamespace(url="/shows/"))):
        assert find_calendar_url("Neck of the Woods", "https://venue.example/") == "https://venue.example/shows/"


@patch("app.ingestion.venue_calendar._head", return_value=httpx.Response(404))
@patch("app.ingestion.venue_calendar._get", return_value=_HOMEPAGE)
def test_find_calendar_url_is_none_when_the_candidate_doesnt_resolve(mock_get, mock_head):
    with patch("app.ingestion.venue_calendar.get_enrichment_llm", _llm(SimpleNamespace(url="/shows/"))):
        assert find_calendar_url("Neck of the Woods", "https://venue.example/") is None


@patch("app.ingestion.venue_calendar._head", return_value=httpx.Response(405))
@patch("app.ingestion.venue_calendar._get")
def test_find_calendar_url_asks_again_with_get_when_the_site_refuses_head(mock_get, mock_head):
    mock_get.side_effect = [_HOMEPAGE, httpx.Response(200)]
    with patch("app.ingestion.venue_calendar.get_enrichment_llm", _llm(SimpleNamespace(url="/shows/"))):
        assert find_calendar_url("Neck of the Woods", "https://venue.example/") == "https://venue.example/shows/"
    assert mock_get.call_args_list[1].args[0] == "https://venue.example/shows/"


@patch("app.ingestion.venue_calendar._get", return_value=_HOMEPAGE)
def test_find_calendar_url_is_none_when_the_llm_finds_nothing_likely(mock_get):
    with patch("app.ingestion.venue_calendar.get_enrichment_llm", _llm(SimpleNamespace(url=None))):
        assert find_calendar_url("Neck of the Woods", "https://venue.example/") is None


@pytest.mark.parametrize("candidate", ["javascript:alert(1)", "http://169.254.169.254/latest/meta-data/",
                                       "http://localhost:11434/api/tags"])
@patch("app.ingestion.venue_calendar._head")
@patch("app.ingestion.venue_calendar._get", return_value=_HOMEPAGE)
def test_find_calendar_url_never_takes_or_fetches_a_non_public_candidate(mock_get, mock_head, candidate):
    with patch("app.ingestion.venue_calendar.get_enrichment_llm", _llm(SimpleNamespace(url=candidate))):
        assert find_calendar_url("Neck of the Woods", "https://venue.example/") is None
    mock_head.assert_not_called()


@pytest.mark.parametrize("failure", [
    {"get": httpx.ConnectError("unreachable")},
    {"get": _html_response("busy", status=503)},
    {"llm_error": RuntimeError("LLM down")},
    {"llm_answer": None},
])
def test_find_calendar_url_fails_temporarily_when_the_homepage_or_the_llm_does_not_answer(failure):
    get = failure.get("get", _HOMEPAGE)
    llm = _llm(failure.get("llm_answer"), failure.get("llm_error"))
    with patch("app.ingestion.venue_calendar._get", side_effect=[get] if isinstance(get, Exception) else None,
               return_value=get), patch("app.ingestion.venue_calendar.get_enrichment_llm", llm):
        with pytest.raises(LookupFailed):
            find_calendar_url("Neck of the Woods", "https://venue.example/")


# ── fetch_calendar_entries: ask the LLM to read the calendar page ──────────────────────────────────────────────

_CALENDAR = "https://venue.example/shows/"
_TODAY = date(2026, 11, 10)


def _entry(**fields):
    return SimpleNamespace(**{"date": "2026-11-14", "title": "Redwood Sirens", "flyer_url": None,
                              "more_info_url": None, "ticket_url": None, **fields})


def _page_with(*entries) -> str:
    """A calendar page holding every URL the entries give, as a real one would."""
    links = [getattr(e, field) for e in entries for field in ("flyer_url", "more_info_url", "ticket_url")]
    return "<html>" + "".join(f'<a href="{url}">x</a>' for url in links if url) + "</html>"


def _read(*entries, page=None, status=200, website_url=None):
    page = _page_with(*entries) if page is None else page
    with patch("app.ingestion.venue_calendar._get", return_value=_html_response(page, status, _CALENDAR)), \
         patch("app.ingestion.venue_calendar.get_enrichment_llm", _llm(SimpleNamespace(entries=list(entries)))):
        return fetch_calendar_entries(_CALENDAR, today=_TODAY, wanted=[(NIGHT, "Redwood Sirens")],
                                      website_url=website_url)


def test_fetch_calendar_entries_resolves_relative_urls_against_the_calendar_page():
    entries = _read(_entry(flyer_url="/flyers/1.jpg", more_info_url="/shows/1",
                           ticket_url="https://www.ticketweb.com/event/redwood-sirens/1"))

    assert entries == [CalendarEntry(date=NIGHT, title="Redwood Sirens",
                                     flyer_url="https://venue.example/flyers/1.jpg",
                                     more_info_url="https://venue.example/shows/1",
                                     ticket_url="https://www.ticketweb.com/event/redwood-sirens/1")]


def test_fetch_calendar_entries_keeps_only_links_that_are_safe_and_belong_to_the_venue_or_a_ticket_seller():
    """The LLM reads an untrusted page: whatever it returns has to pass the same checks a person would make."""
    (entry,) = _read(_entry(flyer_url="data:text/html,<script>alert(1)</script>",
                            more_info_url="https://scalper.example/redwood-sirens",
                            ticket_url="https://scalper.example/buy"))
    assert (entry.flyer_url, entry.more_info_url, entry.ticket_url) == (None, None, None)

    (entry,) = _read(_entry(flyer_url="http://10.0.0.5/flyer.jpg", more_info_url="javascript:alert(1)",
                            ticket_url="http://169.254.169.254/latest/"))
    assert (entry.flyer_url, entry.more_info_url, entry.ticket_url) == (None, None, None)


def test_fetch_calendar_entries_accepts_links_on_the_venues_own_site_under_another_host():
    (entry,) = _read(_entry(more_info_url="https://www.neckofthewoods.example/e/1",
                            ticket_url="https://tickets.neckofthewoods.example/1"),
                     website_url="https://neckofthewoods.example/")
    assert entry.more_info_url == "https://www.neckofthewoods.example/e/1"
    assert entry.ticket_url == "https://tickets.neckofthewoods.example/1"


_SEE_TICKETS = ("https://prod-images.seetickets.us/eyJidWNrZXQiOiJwcm9kLXNpaC5zZWV0aWNrZXRzdXNhLnVzIiwia2V5IjoiNGZkNGJj"
                "OWUtYTdlYi00MmNiLWI1YzMtZWM3NWZkMjgxODhiIn0=")


def test_a_url_the_llm_miscopied_is_taken_as_the_one_on_the_page():
    """Seen live: a See Tickets image path is 300 characters of base64, and the LLM got "sih" as "sph"."""
    miscopied = _SEE_TICKETS.replace("cm9kLXNpaC5", "cm9kLXNwaC5")
    page = f'<img src="{_SEE_TICKETS}"><img src="https://prod-images.seetickets.us/other.jpg">'

    (entry,) = _read(_entry(flyer_url=miscopied), page=page)

    assert entry.flyer_url == _SEE_TICKETS


def test_a_url_found_nowhere_on_the_page_is_dropped():
    (entry,) = _read(_entry(flyer_url="https://venue.example/made-up.jpg", more_info_url="/shows/99"),
                     page='<a href="/about">About</a><img src="https://cdn.example/logo.png">')

    assert (entry.flyer_url, entry.more_info_url) == (None, None)


def test_a_url_as_close_to_two_on_the_page_is_dropped_not_guessed():
    page = '<a href="/shows/1">One</a><a href="/shows/3">Three</a>'

    (entry,) = _read(_entry(more_info_url="/shows/2"), page=page)

    assert entry.more_info_url is None


def test_urls_in_json_ld_srcset_and_css_backgrounds_count_as_on_the_page():
    page = ("""<script type="application/ld+json">{"url": "https:\\/\\/venue.example\\/e\\/1"}</script>"""
            '<img srcset="/f/1-400.jpg 400w, /f/1-800.jpg 800w"><div style="background-image: url(\'/f/2.jpg\')">')

    entries = _read(_entry(more_info_url="https://venue.example/e/1", flyer_url="/f/1-800.jpg"),
                    _entry(date="2026-11-15", flyer_url="/f/2.jpg"), page=page)

    assert [e.flyer_url for e in entries] == [_CALENDAR.replace("/shows/", "") + "/f/1-800.jpg",
                                              _CALENDAR.replace("/shows/", "") + "/f/2.jpg"]
    assert entries[0].more_info_url == "https://venue.example/e/1"


def test_fetch_calendar_entries_with_an_unparseable_date_keeps_the_entry_undated():
    assert _read(_entry(date="sometime in November")) == [CalendarEntry(title="Redwood Sirens")]


def test_a_year_less_date_given_the_wrong_year_is_moved_on_to_the_coming_one():
    """In November, "Jan 9" on the page means next January, not the one gone."""
    assert _read(_entry(date="2026-01-09"))[0].date == date(2027, 1, 9)
    assert _read(_entry(date="2026-11-01"))[0].date == date(2026, 11, 1)   # just gone: left as it is


def test_fetch_calendar_entries_tells_the_llm_today_and_the_shows_it_is_looking_for():
    llm = _llm(SimpleNamespace(entries=[]))
    with patch("app.ingestion.venue_calendar._get", return_value=_html_response("<p>cal</p>", url=_CALENDAR)), \
         patch("app.ingestion.venue_calendar.get_enrichment_llm", llm):
        fetch_calendar_entries(_CALENDAR, today=_TODAY, wanted=[(NIGHT, "Redwood Sirens")])

    prompt = llm.return_value.with_structured_output.return_value.invoke.call_args.args[0]
    assert "Today is Tuesday, November 10, 2026" in prompt
    assert "2026-11-14: Redwood Sirens" in prompt
    assert llm.call_args.kwargs["max_tokens"] >= 4096


def test_a_busy_calendar_is_asked_about_in_batches_never_splitting_a_night():
    """One call for 50 Shows can run out of output tokens and lose the whole answer."""
    from datetime import timedelta as td
    wanted = [(NIGHT + td(days=i), f"Band {i}") for i in range(45)] + [(NIGHT + td(days=19), "Late Band")]
    llm = _llm(SimpleNamespace(entries=[]))
    with patch("app.ingestion.venue_calendar._get", return_value=_html_response("<p>cal</p>", url=_CALENDAR)), \
         patch("app.ingestion.venue_calendar.get_enrichment_llm", llm):
        fetch_calendar_entries(_CALENDAR, today=_TODAY, wanted=wanted)

    prompts = [c.args[0] for c in llm.return_value.with_structured_output.return_value.invoke.call_args_list]
    assert len(prompts) == 3
    night = (NIGHT + td(days=19)).isoformat()
    assert [sum(night in p for p in prompts[:1]), sum(night in p for p in prompts[1:])] == [1, 0]  # both on one call
    for i in range(45):   # each Show asked about exactly once
        assert sum(f": Band {i}\n" in p for p in prompts) == 1


def test_fetch_calendar_entries_raises_calendar_gone_when_the_page_has_gone():
    with pytest.raises(CalendarGone):
        _read(status=404)


@pytest.mark.parametrize("get, llm", [
    (httpx.ConnectError("unreachable"), _llm(SimpleNamespace(entries=[]))),
    (_html_response("busy", 503, _CALENDAR), _llm(SimpleNamespace(entries=[]))),
    (_html_response("<p>cal</p>", 200, _CALENDAR), _llm(error=RuntimeError("down"))),
    (_html_response("<p>cal</p>", 200, _CALENDAR), _llm(None)),
])
def test_fetch_calendar_entries_fails_temporarily_when_the_page_or_the_llm_does_not_answer(get, llm):
    with patch("app.ingestion.venue_calendar._get", side_effect=[get] if isinstance(get, Exception) else None,
               return_value=get), patch("app.ingestion.venue_calendar.get_enrichment_llm", llm):
        with pytest.raises(LookupFailed):
            fetch_calendar_entries(_CALENDAR, today=_TODAY, wanted=[(NIGHT, "Redwood Sirens")])


def test_the_page_is_cut_down_to_its_text_links_images_and_event_data():
    page = """<html><head><meta name="x" content="y"><style>.a{color:red}</style><title>Shows</title></head>
      <body class="home" data-foo="bar"><script>var tracking = 1;</script>
      <script type="application/ld+json">{"@type": "Event", "name": "Redwood Sirens"}</script>
      <svg><path d="M0 0"/></svg>
      <div class="card" style="background-image: url('/flyers/1.jpg')">
        <a href="/shows/1" class="btn" onclick="go()">Redwood Sirens</a>
        <img src="/img/2.jpg" alt="Night Owls" width="300"> <time datetime="2026-11-14">Sat Nov 14</time>
      </div></body></html>"""

    cleaned = _clean_html(page)

    assert '"@type": "Event"' in cleaned
    assert '<a href="/shows/1">Redwood Sirens</a>' in cleaned
    assert '<img src="/img/2.jpg" alt="Night Owls">' in cleaned
    assert 'background="/flyers/1.jpg"' in cleaned and 'datetime="2026-11-14"' in cleaned
    for gone in ("tracking", "color:red", "<path", "onclick", "class=", "<meta", "<body", "<html", "</div>"):
        assert gone not in cleaned
    assert '<div background="/flyers/1.jpg">' in cleaned       # a wrapper is kept only for what it carries
    assert "Shows\n" in cleaned                                 # a block element is a line break


# ── enrich_shows_from_venue_calendars: tying it together for one ingestion run ─────────────────────────────────

NOW = datetime(2026, 11, 10, 12)
_RECENTLY = datetime(2026, 11, 1)


def _band(name):
    return SimpleNamespace(name=name)


def _act(name, position=0):
    return SimpleNamespace(position=position, band=_band(name))


def _venue(name="Neck of the Woods", website_url="https://venue.example/", calendar_url=None, calendar_checked_at=None,
           calendar_read_at=None, calendar_retry_at=None):
    return SimpleNamespace(name=name, website_url=website_url, calendar_url=calendar_url,
                           calendar_checked_at=calendar_checked_at, calendar_read_at=calendar_read_at,
                           calendar_retry_at=calendar_retry_at)


def _found_venue(**fields):
    """A Venue whose calendar was found recently."""
    return _venue(**{"calendar_url": "https://venue.example/shows/", "calendar_checked_at": _RECENTLY, **fields})


def _real_show(venue, id=1, day=NIGHT, headliner="Redwood Sirens", flyer_image_url=None, more_info_url=None,
               ticket_url=None, venue_id=1, created_at=_RECENTLY, flyer_gone_url=None):
    return SimpleNamespace(id=id, venue_id=venue_id, venue=venue, date=day, acts=[_act(headliner)],
                           flyer_image_url=flyer_image_url, more_info_url=more_info_url, ticket_url=ticket_url,
                           created_at=created_at, flyer_gone_url=flyer_gone_url)


def _enrich(shows, **kwargs):
    return enrich_shows_from_venue_calendars(shows, today=_TODAY, now=NOW, **kwargs)


@patch("app.ingestion.venue_calendar.fetch_calendar_entries", return_value=[])
@patch("app.ingestion.venue_calendar.find_calendar_url")
def test_a_correction_short_circuits_discovery_entirely(mock_find, mock_fetch):
    venue = _venue(name="Some Venue")
    show = _real_show(venue)
    CORRECTIONS["some-venue"] = VenueCorrection(calendar_url="https://corrected.example/shows/")
    try:
        _enrich([show])
    finally:
        del CORRECTIONS["some-venue"]

    mock_find.assert_not_called()
    assert venue.calendar_url == "https://corrected.example/shows/"
    assert venue.calendar_checked_at is not None
    assert mock_fetch.call_args.args == ("https://corrected.example/shows/",)


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
@patch("app.ingestion.venue_calendar.find_calendar_url", return_value=None)
def test_a_venue_with_no_calendar_found_is_marked_checked_without_reading(mock_find, mock_fetch):
    venue = _venue()

    assert _enrich([_real_show(venue)]) == 0

    assert (venue.calendar_url, venue.calendar_checked_at) == (None, NOW)
    mock_fetch.assert_not_called()


@patch("app.ingestion.venue_calendar.fetch_calendar_entries", return_value=[])
@patch("app.ingestion.venue_calendar.find_calendar_url")
def test_a_venue_checked_recently_is_not_looked_up_again(mock_find, mock_fetch):
    _enrich([_real_show(_found_venue())])
    mock_find.assert_not_called()


@patch("app.ingestion.venue_calendar.fetch_calendar_entries", return_value=[])
@patch("app.ingestion.venue_calendar.find_calendar_url", return_value="https://venue.example/events/")
def test_a_venue_checked_over_a_month_ago_is_looked_up_again_and_its_moved_calendar_read(mock_find, mock_fetch):
    venue = _found_venue(calendar_checked_at=datetime(2026, 10, 1), calendar_read_at=_RECENTLY)

    _enrich([_real_show(venue)])

    assert (venue.calendar_url, venue.calendar_checked_at) == ("https://venue.example/events/", NOW)
    assert mock_fetch.call_args.args == ("https://venue.example/events/",)


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
@patch("app.ingestion.venue_calendar.find_calendar_url", side_effect=LookupFailed("homepage down"))
def test_a_temporary_failure_records_nothing_but_holds_the_venue_back_a_day(mock_find, mock_fetch):
    venue = _venue()
    show = _real_show(venue)

    _enrich([show])

    assert venue.calendar_checked_at is None
    assert venue.calendar_retry_at == NOW + timedelta(days=1)
    mock_find.reset_mock()
    enrich_shows_from_venue_calendars([show], today=_TODAY, now=NOW + timedelta(hours=1))
    mock_find.assert_not_called()
    enrich_shows_from_venue_calendars([show], today=_TODAY, now=NOW + timedelta(days=1, hours=1))
    mock_find.assert_called_once()


@patch("app.ingestion.venue_calendar.find_calendar_url")
def test_a_venue_without_a_website_is_left_to_look_up_once_it_has_one(mock_find):
    venue = _venue(website_url=None)

    _enrich([_real_show(venue)])

    mock_find.assert_not_called()
    assert venue.calendar_checked_at is None


@patch("app.ingestion.venue_calendar.fetch_calendar_entries", return_value=[])
def test_a_calendar_read_recently_is_not_read_again_until_a_new_show_turns_up(mock_fetch):
    venue = _found_venue(calendar_read_at=datetime(2026, 11, 9))
    seen = _real_show(venue, created_at=datetime(2026, 11, 5))

    _enrich([seen])
    mock_fetch.assert_not_called()

    _enrich([seen, _real_show(venue, id=2, headliner="Night Owls", created_at=datetime(2026, 11, 10))])
    mock_fetch.assert_called_once()
    assert mock_fetch.call_args.kwargs["wanted"] == [(NIGHT, "Night Owls"), (NIGHT, "Redwood Sirens")]
    assert venue.calendar_read_at == NOW


@patch("app.ingestion.venue_calendar.fetch_calendar_entries", return_value=[])
def test_a_calendar_is_read_again_weekly_while_shows_still_miss_something(mock_fetch):
    venue = _found_venue(calendar_read_at=datetime(2026, 11, 2))

    _enrich([_real_show(venue, created_at=datetime(2026, 10, 1))])

    mock_fetch.assert_called_once()


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
def test_shows_with_a_flyer_and_more_info_link_or_already_past_never_have_the_calendar_read(mock_fetch):
    """A missing ticket link alone doesn't count: most Shows never get one, and every calendar would be read."""
    venue = _found_venue()
    complete = _real_show(venue, flyer_image_url="shows/1-a.webp", more_info_url="https://venue.example/shows/1")
    past = _real_show(venue, id=2, day=date(2026, 11, 1))

    assert _enrich([complete, past]) == 0
    mock_fetch.assert_not_called()


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
def test_a_matched_entry_fills_the_real_shows_gaps(mock_fetch):
    venue = _found_venue()
    show = _real_show(venue, ticket_url="https://steves-pick.example/1")  # the List's own ticket link
    mock_fetch.return_value = [CalendarEntry(date=NIGHT, title="Redwood Sirens",
                                             flyer_url="https://venue.example/flyer.jpg",
                                             more_info_url="https://venue.example/shows/1",
                                             ticket_url="https://venue.example/tickets/1")]

    assert _enrich([show]) == 1

    assert show.flyer_image_url == "https://venue.example/flyer.jpg"
    assert show.more_info_url == "https://venue.example/shows/1"
    assert show.ticket_url == "https://steves-pick.example/1"  # kept: never overwritten


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
def test_a_flyer_url_that_was_gone_is_not_taken_again_but_the_rest_of_the_entry_is(mock_fetch):
    venue = _found_venue()
    show = _real_show(venue, flyer_gone_url="https://venue.example/dead.jpg")
    mock_fetch.return_value = [CalendarEntry(date=NIGHT, title="Redwood Sirens", flyer_url="https://venue.example/dead.jpg",
                                             more_info_url="https://venue.example/shows/1")]

    assert _enrich([show]) == 1

    assert show.flyer_image_url is None
    assert show.more_info_url == "https://venue.example/shows/1"


@patch("app.ingestion.venue_calendar.fetch_calendar_entries", side_effect=CalendarGone("gone"))
def test_a_calendar_page_that_has_gone_is_looked_for_again(mock_fetch):
    venue = _found_venue()

    _enrich([_real_show(venue)])

    assert venue.calendar_checked_at is None


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
def test_one_venues_failure_does_not_stop_the_others(mock_fetch):
    broken = _found_venue(name="Broken Venue", calendar_url="https://broken.example/")
    ok = _found_venue(name="OK Venue", calendar_url="https://ok.example/")
    broken_show = _real_show(broken, id=1, headliner="Doomed", venue_id=1)
    ok_show = _real_show(ok, id=2, venue_id=2)

    def fetch(url, **kwargs):
        if url == "https://broken.example/":
            raise RuntimeError("boom")
        return [CalendarEntry(date=NIGHT, title="Redwood Sirens", flyer_url="https://ok.example/flyer.jpg")]
    mock_fetch.side_effect = fetch

    assert _enrich([broken_show, ok_show]) == 1
    assert ok_show.flyer_image_url == "https://ok.example/flyer.jpg"
    assert broken_show.flyer_image_url is None
    assert broken.calendar_retry_at == NOW + timedelta(days=1)


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
def test_a_slow_venue_is_left_for_the_next_run_rather_than_holding_up_the_step(mock_fetch):
    slow = _found_venue(name="Slow Venue", calendar_url="https://slow.example/")
    quick = _found_venue(name="Quick Venue", calendar_url="https://quick.example/")
    slow_show, quick_show = _real_show(slow, id=1, venue_id=1), _real_show(quick, id=2, venue_id=2)

    def fetch(url, **kwargs):
        if url == "https://slow.example/":
            time.sleep(1)
        return [CalendarEntry(date=NIGHT, title="Redwood Sirens", flyer_url=f"{url}flyer.jpg")]
    mock_fetch.side_effect = fetch

    started = time.monotonic()
    assert _enrich([slow_show, quick_show], budget=0.3) == 1
    assert time.monotonic() - started < 0.9
    assert quick_show.flyer_image_url == "https://quick.example/flyer.jpg"
    assert slow_show.flyer_image_url is None and slow.calendar_read_at is None


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
def test_an_already_complete_early_show_does_not_steal_an_entry_meant_for_it_alone(mock_fetch):
    """Regression: match_calendar's same-night disambiguation needs every Show that night, not just the ones
    still missing something. If the already-complete "early" Show were left out of the candidate pool, the
    "late" Show (still missing its flyer) would look like the *only* candidate for this entry -- which is
    actually the early Show's -- and wrongly take its flyer."""
    venue = _found_venue()
    early = _real_show(venue, id=1, headliner="Early Birds", flyer_image_url="shows/1-a.webp",
                       more_info_url="https://venue.example/shows/1", ticket_url="https://tix.example/1")
    late = _real_show(venue, id=2, headliner="Night Owls")  # still missing everything
    mock_fetch.return_value = [CalendarEntry(date=NIGHT, title="Early Birds", flyer_url="https://venue.example/early.jpg")]

    assert _enrich([early, late]) == 0

    assert late.flyer_image_url is None                      # never mistaken for the early Show's entry
    assert early.flyer_image_url == "shows/1-a.webp"          # untouched: it already had one


@patch("app.ingestion.venue_calendar.fetch_calendar_entries")
@patch("app.ingestion.venue_calendar.find_calendar_url")
def test_without_an_llm_key_no_venue_is_looked_at_or_marked_checked(mock_find, mock_fetch, monkeypatch):
    """Otherwise a run without the key would mark every Venue as having no calendar, for good."""
    from app.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    venue = _found_venue(calendar_checked_at=None)

    assert _enrich([_real_show(venue)]) == 0

    mock_find.assert_not_called()
    mock_fetch.assert_not_called()
    assert venue.calendar_checked_at is None
