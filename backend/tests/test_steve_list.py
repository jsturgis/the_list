"""Tests for the List page (app/ingestion/steve_list.py): fetching it, and its listings as upsert-ready Shows."""
import hashlib
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.ingestion import steve_list
from app.ingestion.steve_list import ListError, edition_title, fetch_list, list_page, list_shows

_CONTENT = (Path(__file__).parent / "fixtures" / "the_list.txt").read_bytes()
_HEADER = "funk-punk-thrash-ska      Upcoming shows of Interest      November 13, 2026\n\n"


@pytest.fixture(scope="module")
def shows() -> list[dict]:
    return list_shows(_CONTENT.decode())


def _find(shows: list[dict], headliner: str) -> dict:
    return next(s for s in shows if s["bands"][:1] == [headliner])


def _show(listing: str, monkeypatch) -> dict:
    monkeypatch.setattr(steve_list, "_MIN_SHOWS", 1)
    [show] = list_shows(_HEADER + listing + "\n")
    return show


# ── the page ──────────────────────────────────────────────────────────────────


def _serve(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(steve_list.httpx, "get", lambda url, **kw: real(
        transport=httpx.MockTransport(handler), follow_redirects=kw.get("follow_redirects", False)).get(url))


def test_fetch_list_returns_the_page_its_hash_and_its_edition_date(monkeypatch):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=_CONTENT)

    _serve(monkeypatch, handler)

    page = fetch_list()

    assert requested == ["https://stevelist.com/list"]
    assert page.text == _CONTENT.decode()
    assert page.sha256 == hashlib.sha256(_CONTENT).hexdigest()
    assert page.edition_date == date(2026, 11, 13)


def test_any_change_to_the_page_changes_its_hash():
    assert list_page(_CONTENT.replace(b"$18/$20", b"$18/$22")).sha256 != list_page(_CONTENT).sha256


def test_fetch_list_fails_when_the_site_is_down(monkeypatch):
    _serve(monkeypatch, lambda request: httpx.Response(503))
    with pytest.raises(ListError, match="couldn't fetch https://stevelist.com/list"):
        fetch_list()


def test_fetch_list_fails_when_the_page_isnt_the_list(monkeypatch):
    _serve(monkeypatch, lambda request: httpx.Response(200, content=b"<html><body>Coming soon</body></html>"))
    with pytest.raises(ListError, match="isn't the List"):
        fetch_list()


def test_a_page_cut_short_isnt_taken_for_the_list():
    cut_short = _CONTENT.decode().split("nov 13 fri Jo Koy")[0]
    with pytest.raises(ListError, match="only 3 listings"):
        list_shows(cut_short)


def test_edition_title():
    assert edition_title(date(2026, 11, 13)) == "The List for Nov 13, 2026"
    assert edition_title(date(2027, 1, 1)) == "The List for Jan 1, 2027"


# ── listings as Shows ─────────────────────────────────────────────────────────


def test_a_listing_becomes_an_upsert_ready_show(shows):
    assert _find(shows, "Charger") == {
        "date": date(2026, 11, 13),
        "bands": ["Charger", "Ancient Rage", "Phantasmal Abyss", "Commoner"],
        "act_notes": ["record release", None, None, None],
        # The List only names a Band: its genres, links and photo come from the services.
        "band_enrichment": [(name, {"genres": []}) for name in ("Charger", "Ancient Rage", "Phantasmal Abyss", "Commoner")],
        "venue_name": "Gilman Brewing Co.",
        "city": "Berkeley",
        "address": "912 Gilman Street, Berkeley",
        "venue_website": None,
        "status": "upcoming",
        "age_restriction": "a/a",
        "price_raw": "$20/$25",
        "door_time": "7pm",
        "set_time": "8pm",
        "notes": None,
        "is_recommended": False, "will_sell_out": False, "is_pit": False, "is_drink_tickets": False,
        "is_no_reentry": False, "is_sold_out": False, "is_matinee": False, "is_benefit": False,
        "raw_text": ("nov 13 fri Charger (record release), Ancient Rage, Phantasmal Abyss, Commoner\n"
                     "       at Gilman Brewing Co., 912 Gilman Street, Berkeley a/a $20/$25 7pm/8pm"),
    }


def test_shows_are_only_what_the_list_says(shows):
    """Nothing about tickets or the Venue beyond its name, city and street: upsert keeps what a Show already has."""
    assert not {"ticket_url", "ticket_provider", "special_event", "benefit_cause"} & set(shows[0])


def test_steves_cities_go_by_their_names(shows):
    assert _find(shows, "L7")["city"] == "San Francisco"   # "S.F."
    assert _find(shows, "A SKy So Black")["city"] == "Berkeley"
    assert _find(shows, "Michael Nau")["city"] == "Santa Cruz"


def test_a_misspelt_city_is_read_as_the_one_meant(shows):
    assert _find(shows, "Membership Meeting")["city"] == "Berkeley"   # "Berkeleyu"


def test_a_city_without_a_comma_before_it_is_split_from_the_venue(shows):
    tyla = _find(shows, "Tyla")       # "at the Fox Theater Oakland a/a 8pm"
    assert (tyla["venue_name"], tyla["city"]) == ("the Fox Theater", "Oakland")
    kings = _find(shows, "Kings Of Leon")   # "at Shoreline Amphitheater Mountain View a/a"
    assert (kings["venue_name"], kings["city"]) == ("Shoreline Amphitheater", "Mountain View")


def test_what_follows_the_city_goes_to_the_notes(shows):
    chorus = _find(shows, "San Francisco Gay Men's Chorus")
    # "at the Castro, S.F. a/a $48 2:30pm/3pm, 5pm/5:30pm and 7:30pm/8pm shows"
    assert (chorus["venue_name"], chorus["city"]) == ("the Castro", "San Francisco")
    assert (chorus["door_time"], chorus["set_time"]) == ("2:30pm", "3pm")
    assert chorus["notes"] == "5pm/5:30pm and 7:30pm/8pm shows"
    assert chorus["act_notes"] == ["3 shows"]


def test_a_second_age_goes_to_the_notes(shows):
    virji = _find(shows, "Sammy Virji")   # "a/a 18+ $99.88 7pm/8pm # (was at Cow Palace)"
    assert (virji["age_restriction"], virji["notes"]) == ("a/a", "was at Cow Palace; 18+")


def test_a_city_we_dont_know_is_kept(monkeypatch):
    show = _show("nov 20 fri Band A at Rio Nido Roadhouse, 14540 Canyon 2 Road, Rio Nido a/a 6pm", monkeypatch)
    assert (show["city"], show["address"]) == ("Rio Nido", "14540 Canyon 2 Road, Rio Nido")


def test_sold_out_matinee_and_benefit_are_read_from_the_listing(shows, monkeypatch):
    assert _find(shows, "Jon Spencer")["is_sold_out"] is True       # "(sold out)"
    assert _find(shows, "L7")["is_sold_out"] is False
    assert _find(shows, "Punk Yoga")["is_matinee"] is True          # doors at noon
    assert _find(shows, "Membership Meeting")["is_matinee"] is True   # 4pm
    assert _find(shows, "L7")["is_matinee"] is False                # 7pm
    benefit = _show("nov 20 fri Band A at the Chapel, S.F. a/a $20 8pm (Benefit Wildland Firefighters)", monkeypatch)
    assert (benefit["is_benefit"], benefit["notes"]) == (True, "Benefit Wildland Firefighters")
    assert _find(shows, "L7")["is_benefit"] is False


def test_statuses(shows):
    assert _find(shows, "Francisca Valenzuela")["status"] == "postponed"
    assert _find(shows, "Prayers")["status"] == "cancelled"
    incorrect = next(s for s in shows if "INCORRECT LISTING" in s["raw_text"])
    assert (incorrect["status"], incorrect["notes"], incorrect["bands"]) == ("cancelled", "incorrect listing", [])


# ── Shows on the wrong day (app/ingestion/show_corrections.py) ───────────────

def test_a_listing_on_the_wrong_day_is_read_as_the_venues_day(monkeypatch):
    show = _show("nov 30 mon Time Spent /Driving, The New Trust, Midcourse Correction\n"
                 "       at Kilowatt, S.F. 21+ $10 7pm", monkeypatch)
    assert show["date"] == date(2026, 11, 29)


def test_only_the_corrected_listing_moves(monkeypatch):
    other_band = _show("nov 30 mon Midcourse Correction at Kilowatt, S.F. 21+ $10 7pm", monkeypatch)
    other_venue = _show("nov 30 mon Time Spent Driving at the Independent, S.F. 21+ $10 7pm", monkeypatch)
    assert (other_band["date"], other_venue["date"]) == (date(2026, 11, 30), date(2026, 11, 30))


def test_the_show_added_on_the_right_day_becomes_the_lists_and_the_wrong_days_goes(db, monkeypatch):
    from app.ingestion.upsert import remove_unlisted_shows, upsert_shows
    from app.models.show import Show

    from app.ingestion import upsert

    monkeypatch.setattr(steve_list, "_MIN_SHOWS", 1)
    monkeypatch.setattr(upsert, "_MAX_UNLISTED_SHARE", 1)   # one of the page's hundreds, not one of two
    listing = ("nov 30 mon Time Spent /Driving, The New Trust, Midcourse Correction\n"
               "       at Kilowatt, S.F. 21+ $10 7pm\n")
    wrong_day = {**_show(listing, monkeypatch), "date": date(2026, 11, 30)}   # as stored before the correction
    (stored,) = upsert_shows(db, [wrong_day])
    ticket = ("https://dice.fm/event/nylyn5-time-spent-driving-and-the-new-trust-29th-nov-kilowatt-san-francisco"
              "-tickets")
    (added,) = upsert_shows(db, [{**wrong_day, "date": date(2026, 11, 29), "bands": ["Time Spent Driving",
                                  "The New Trust"], "source": "page", "ticket_url": ticket, "raw_text": None}])

    listed = upsert_shows(db, list_shows(_HEADER + listing))
    assert [s.id for s in listed] == [added.id]
    assert remove_unlisted_shows(db, listed, date(2026, 11, 13)) == [stored.id]
    show = db.get(Show, added.id)
    assert (show.date, show.source, show.ticket_url) == (date(2026, 11, 29), "list", ticket)
    assert [a.band.name for a in sorted(show.acts, key=lambda a: a.position)] == [
        "Time Spent /Driving", "The New Trust", "Midcourse Correction"]
