"""One event Steve lists and an event page added, spelled differently (app/ingestion/upsert.py, fold_added_shows):
the List's Show stays, with the added one's ticket link, and the added one goes."""
from __future__ import annotations

from datetime import date

import pytest

from app.ingestion.upsert import fold_added_shows, same_event, upsert_shows
from app.models.show import Show

_STEVE = ["Sunamo", "No Pressure", "Outta Pocket", "Middrift", "Small Crush", "Seltzer", "Forced To Suffer"]
_BANDSINTOWN = ["Sunami", "No Pressure", "Midrift", "Outta Pocket", "Small Crush", "Seltzer"]
_TM = "https://www.ticketmaster.com/sunami-san-jose-california-12-26-2026/event/1C006550FA24DFD7"


def _listing(bands, *, source="list", door_time="5:30pm", venue="San Jose Civic", day=date(2026, 12, 26), **extra):
    return {"date": day, "bands": bands, "act_notes": [None] * len(bands),
            "band_enrichment": [(b, {"genres": []}) for b in bands], "venue_name": venue, "city": "San Jose",
            "door_time": door_time, "set_time": None, "price_raw": "$35/$40" if source == "list" else None,
            "age_restriction": "a/a" if source == "list" else None, "status": "upcoming", "source": source,
            "is_recommended": False, "will_sell_out": False, "is_pit": source == "list", "is_drink_tickets": False,
            "is_no_reentry": source == "list", "is_sold_out": False, "is_matinee": False, "is_benefit": False,
            "notes": None, "raw_text": " ".join(bands), **extra}


def _added(bands=_BANDSINTOWN, door_time="6:30pm", **extra):
    return _listing(bands, source="page", door_time=door_time, ticket_provider="ticketmaster.com", ticket_url=_TM,
                    **extra)


@pytest.mark.parametrize("first, then", [("list", "page"), ("page", "list")])
def test_an_event_steve_lists_and_one_added_spelled_otherwise_become_the_lists_show(db, first, then):
    """Whichever came first: the added one is folded in when either is stored."""
    data = {"list": _listing(_STEVE), "page": _added()}
    upsert_shows(db, [data[first]])
    stored, folded = fold_added_shows(db, upsert_shows(db, [data[then]]))

    (show,) = db.query(Show).all()
    assert show.source == "list"
    assert [a.band.name for a in show.acts] == _STEVE   # Steve's lineup and details stay
    assert (show.price_min, show.is_pit, show.door_time.strftime("%H:%M")) == (35, True, "17:30")
    assert (show.ticket_provider, show.ticket_url) == ("ticketmaster.com", _TM)
    assert stored == [show] and len(folded) == 1


def test_the_lists_ticket_link_isnt_replaced(db):
    upsert_shows(db, [_listing(_STEVE, ticket_provider="TicketWeb", ticket_url="https://www.ticketweb.com/event/1")])
    fold_added_shows(db, upsert_shows(db, [_added()]))
    (show,) = db.query(Show).all()
    assert show.ticket_provider == "TicketWeb"


@pytest.mark.parametrize("bands", [
    ["Headliner Band", "Opener"],                     # nothing in common
    ["Another Act", "Yet Another", "No Pressure"],    # one Band of three in common: under half
])
def test_another_event_at_the_venue_that_day_isnt_folded(db, bands):
    upsert_shows(db, [_listing(_STEVE)])
    fold_added_shows(db, upsert_shows(db, [_added(bands)]))
    assert sorted(s.source for s in db.query(Show).all()) == ["list", "page"]


def test_a_misspelt_headliner_alone_is_the_same_event(db):
    upsert_shows(db, [_listing(["The Linda Lindas"])])
    fold_added_shows(db, upsert_shows(db, [_added(["The Linda Lindaz"])]))
    assert [s.source for s in db.query(Show).all()] == ["list"]


def test_shows_elsewhere_or_another_day_arent_the_same_event(db):
    upsert_shows(db, [_listing(_STEVE)])
    fold_added_shows(db, upsert_shows(db, [_added(day=date(2026, 12, 27)), _added(venue="The Ritz")]))
    assert sorted(s.source for s in db.query(Show).all()) == ["list", "page", "page"]


def test_with_an_early_and_a_late_show_only_the_one_at_its_time_takes_it(db):
    upsert_shows(db, [_listing(_STEVE, door_time="1pm"), _listing(_STEVE, door_time="7pm")])
    fold_added_shows(db, upsert_shows(db, [_added(door_time="5pm")]))   # neither: left alone
    assert sorted(s.source for s in db.query(Show).all()) == ["list", "list", "page"]
    fold_added_shows(db, upsert_shows(db, [_added(door_time="7pm")]))   # the late one's
    shows = db.query(Show).order_by(Show.door_time).all()
    assert [(s.door_time.hour, s.source, s.ticket_url) for s in shows] == [
        (13, "list", None), (17, "page", _TM), (19, "list", _TM)]


def test_two_shows_from_elsewhere_are_never_folded_together(db):
    upsert_shows(db, [_added()])
    fold_added_shows(db, upsert_shows(db, [_added(_STEVE, door_time="8pm")]))
    assert len(db.query(Show).all()) == 2


def test_same_event_compares_headliners_and_lineups(db):
    listed, added = upsert_shows(db, [_listing(_STEVE), _added()])
    assert same_event(added, listed)


@pytest.mark.parametrize("listed, added", [
    (["Victor Wooten And The Wooten Brothers"], ["Victor Wooten", "Regi Wooten", "Roy Wooten", "Joseph Wooten"]),
    (["Victor Wooten"], ["Victor Wooten & The Wooten Brothers"]),
    (["Bob Mould with Jason Narducy"], ["Bob Mould"]),
])
def test_a_headliner_and_its_whole_billing_are_the_same_event(db, listed, added):
    """Steve lists a billing as one name where a page names its first act (The UC Theatre, Dec 10 2026)."""
    upsert_shows(db, [_listing(listed)])
    fold_added_shows(db, upsert_shows(db, [_added(added)]))
    assert [s.source for s in db.query(Show).all()] == ["list"]


@pytest.mark.parametrize("listed, added", [
    (["Wooten Brothers"], ["Wooten Brothers Tribute Band"]),   # no billing join
    (["Victor Wooten"], ["Victor Wooten-Andrews"]),           # a joined word isn't a join
    (["Victor Wooten"], ["Victor Wootenand Friends"]),
    (["Regi Wooten"], ["Victor Wooten and Regi Wooten"]),     # the join must follow the whole headliner
])
def test_a_headliner_that_only_begins_another_name_isnt_the_same_event(db, listed, added):
    upsert_shows(db, [_listing(listed)])
    fold_added_shows(db, upsert_shows(db, [_added(added)]))
    assert sorted(s.source for s in db.query(Show).all()) == ["list", "page"]


def test_a_band_named_as_a_billing_goes_to_its_own_show_not_the_one_it_begins(db):
    """Two rooms: Iron and Wine in one, a band called Iron in the other. An added Iron Show is Iron's."""
    upsert_shows(db, [_listing(["Iron and Wine"], door_time="7pm"), _listing(["Iron"], door_time="8pm")])
    fold_added_shows(db, upsert_shows(db, [_added(["Iron"], door_time="7pm")]))
    shows = {s.id: s for s in db.query(Show).all()}
    assert sorted(s.source for s in shows.values()) == ["list", "list"]
    (iron,) = [s for s in shows.values() if s.acts[0].band.name == "Iron"]
    assert iron.ticket_url == _TM
