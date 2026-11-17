"""Tests for adding a Show from a TicketWeb event page: reading the page (app/ingestion/ticketweb.py), storing it
alongside the List's Shows (the List wins), and `python -m app.cli add-event`."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.cli import main
from app.ingestion.ticketweb import EventError, event_show, event_url, fetch_event
from app.ingestion.upsert import upsert_shows
from app.models.band import Band
from app.models.show import AgeRestriction, Show, ShowStatus
from app.models.venue import Region, Venue
from app.scheduler import ingest_shows

_URL = "https://www.ticketweb.com/event/teenage-bottlerocket-w-brendan-kelly-moes-alley-tickets/14446334"
# A trimmed copy of the event's page: its JSON-LD and the date and doors.
_PAGE = (Path(__file__).parent / "fixtures" / "ticketweb_event.html").read_text()


def _page_with(**changes) -> str:
    """The event's page with its JSON-LD event changed (a key set to None is removed)."""
    start, rest = _PAGE.split('<script type="application/ld+json">')
    block, end = rest.split("</script>", 1)
    event = {**json.loads(block), **changes}
    event = {k: v for k, v in event.items() if v is not None}
    return f'{start}<script type="application/ld+json">{json.dumps(event)}</script>{end}'


# ── reading the page ──────────────────────────────────────────────────────────

def test_reads_the_show_from_the_event_page():
    show = event_show(_PAGE, _URL)

    assert show["source"] == "ticketweb"
    assert show["bands"] == ["Teenage Bottlerocket", "Brendan Kelly"]
    assert show["date"] == date(2027, 1, 21)
    assert (show["door_time"], show["set_time"]) == ("7pm", "8pm")
    assert (show["venue_name"], show["city"]) == ("Moe's Alley", "Santa Cruz")
    assert show["address"] == "1535 Commercial Way, Santa Cruz"
    assert show["venue_website"] == "https://www.moesalley.com"
    assert show["price_raw"] == "$20/$25"   # the face value, not the $25.16 with fees
    assert show["age_restriction"] == "21+"
    assert show["status"] == "upcoming"
    assert (show["is_sold_out"], show["is_matinee"]) == (False, False)
    assert (show["ticket_provider"], show["ticket_url"]) == ("TicketWeb", _URL)


def test_a_link_from_elsewhere_loses_its_tracking():
    assert event_url(_URL + "?utm_medium=affiliate&irgwc=1&utm_source=219208-Bandsintown") == _URL


def test_takes_the_lineup_from_the_name_when_no_performers_are_given():
    show = event_show(_page_with(performers=None), _URL)
    assert show["bands"] == ["Teenage Bottlerocket", "Brendan Kelly"]


def test_takes_the_door_time_from_the_description_when_the_page_has_none():
    page = _page_with().replace(">Doors open<", "><")
    assert event_show(page, _URL)["door_time"] == "7pm"


def test_an_event_with_one_time_lists_it_as_the_door_time():
    page = _page_with(description="21+").replace(">Doors open<", "><")
    show = event_show(page, _URL)
    assert (show["door_time"], show["set_time"]) == ("8pm", None)


@pytest.mark.parametrize("status, expected", [("EventCancelled", "cancelled"),
                                              ("https://schema.org/EventPostponed", "postponed"),
                                              ("EventRescheduled", "upcoming")])
def test_reads_the_events_status(status, expected):
    assert event_show(_page_with(eventStatus=status), _URL)["status"] == expected


def test_a_sold_out_event_is_sold_out():
    offers = {"availability": "http://schema.org/SoldOut", "price": "25.16"}
    assert event_show(_page_with(offers=offers), _URL)["is_sold_out"]


def test_takes_the_price_with_fees_when_the_description_has_none():
    without = {"description": "21+"}
    assert event_show(_page_with(**without), _URL)["price_raw"] == "$25.16"
    assert event_show(_page_with(**without, offers=[{"lowPrice": "20", "highPrice": "25"}]), _URL)["price_raw"] == \
        "$20/$25"
    assert event_show(_page_with(**without, offers={"price": "0"}), _URL)["price_raw"] == "free"


def test_takes_one_face_value():
    assert event_show(_page_with(description="Doors 8pm<br />$15<br />21+"), _URL)["price_raw"] == "$15"


def test_a_dollar_amount_in_a_paragraph_isnt_the_price():
    prose = "The band raised $10,000 for their tour van and are bringing it all the way across the country to play."
    assert event_show(_page_with(description=prose), _URL)["price_raw"] == "$25.16"


def test_refuses_an_event_outside_the_bay_area():
    location = {"name": "Hi-Dive", "address": {"streetAddress": "7 S Broadway", "addressLocality": "Denver"}}
    with pytest.raises(EventError, match="Denver"):
        event_show(_page_with(location=location), _URL)


def test_refuses_a_page_with_no_event_on_it():
    with pytest.raises(EventError, match="no event"):
        event_show("<html><body>Your browsing activity has been paused!</body></html>", _URL)


def test_refuses_a_page_that_isnt_ticketweb():
    with pytest.raises(EventError, match="isn't a TicketWeb page"):
        fetch_event("https://www.example.com/event/14446334")


# ── storing it ────────────────────────────────────────────────────────────────

def _listing(**changes) -> dict:
    """Moe's Alley's Show as Steve would list it."""
    return {**event_show(_PAGE, _URL), "source": "list", "ticket_provider": None, "ticket_url": None,
            "price_raw": "$20/$25", "door_time": "8pm", "set_time": None, "is_recommended": True, **changes}


def test_an_event_is_stored_as_a_show_from_ticketweb(db):
    (show,) = upsert_shows(db, [event_show(_PAGE, _URL)])

    assert show.source == "ticketweb"
    assert [a.band.name for a in show.acts] == ["Teenage Bottlerocket", "Brendan Kelly"]
    assert (show.door_time, show.set_time) == (time(19, 0), time(20, 0))
    assert (show.price_min, show.price_max, show.age_restriction, show.status) == (20.0, 25.0, AgeRestriction.plus_21, ShowStatus.upcoming)
    assert show.venue.region == Region.santa_cruz
    assert show.ticket_url == _URL


def test_an_event_steve_lists_only_adds_its_ticket_link(db):
    (listed,) = upsert_shows(db, [_listing()])
    (show,) = upsert_shows(db, [event_show(_PAGE, _URL)])   # doors at 7pm, where Steve lists the 8pm show time

    assert show.id == listed.id
    assert db.query(Show).count() == 1
    assert (show.source, show.is_recommended, show.price_min, show.door_time) == ("list", True, 20.0, time(20, 0))
    assert (show.ticket_provider, show.ticket_url) == ("TicketWeb", _URL)


def test_an_event_isnt_taken_for_another_show_at_that_time(db):
    """A Venue with two rooms: Steve lists one Show, the event is the other one at the same time."""
    upsert_shows(db, [_listing(bands=["Swingin' Utters"], band_enrichment=[("Swingin' Utters", {"genres": []})],
                               act_notes=[None], door_time="7pm")])
    upsert_shows(db, [event_show(_PAGE, _URL)])

    shows = db.query(Show).order_by(Show.id).all()
    assert [(s.source, s.acts[0].band.name, s.ticket_url) for s in shows] == [
        ("list", "Swingin' Utters", None), ("ticketweb", "Teenage Bottlerocket", _URL)]


def test_a_show_from_ticketweb_is_the_lists_once_steve_lists_it(db):
    upsert_shows(db, [event_show(_PAGE, _URL)])
    (show,) = upsert_shows(db, [_listing(door_time="7pm", set_time="8pm")])

    assert db.query(Show).count() == 1
    assert (show.source, show.is_recommended, show.price_min) == ("list", True, 20.0)
    assert show.ticket_url == _URL   # the List has no ticket links: the event's is kept


def test_adding_an_event_again_updates_it(db):
    upsert_shows(db, [event_show(_PAGE, _URL)])
    (show,) = upsert_shows(db, [event_show(_page_with(eventStatus="EventCancelled"), _URL)])

    assert db.query(Show).count() == 1
    assert show.status == ShowStatus.cancelled


def _venue_data(name, city, street=None, use_llm=True):
    return {"address": f"{street}, {city}, CA 95065, USA", "google_place_id": f"ChIJ-{name}", "city": city}


@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", return_value={"genres": ["punk"], "mb_genres": True, "spotify_url": None,
                                                    "soundcloud_url": None, "bandcamp_url": None})
@patch("app.scheduler.split_joint_name", side_effect=lambda name: [name])
@patch("app.scheduler.save_band_photos", return_value=0)
@patch("app.scheduler.commons_photo", return_value=None)
@patch("app.scheduler.discogs_artist", return_value=None)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_an_events_new_venue_and_bands_are_looked_up_as_the_lists_are(
        mock_batch, mock_discogs, mock_commons, mock_photos, mock_split, mock_band, mock_venue, db):
    (show,) = await ingest_shows(db, [event_show(_PAGE, _URL)])

    venue = db.query(Venue).one()
    assert (venue.name, venue.google_place_id) == ("Moe's Alley", "ChIJ-Moe's Alley")
    bottlerocket = db.query(Band).filter(Band.name == "Teenage Bottlerocket").one()
    assert bottlerocket.genres == ["punk"]
    assert bottlerocket.enriched_at is not None
    assert show.source == "ticketweb"
    mock_batch.assert_called_once()


@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.split_joint_name", side_effect=lambda name: [name])
@patch("app.scheduler.save_band_photos", return_value=0)
@patch("app.scheduler.commons_photo", return_value=None)
@patch("app.scheduler.discogs_artist", return_value=None)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_an_events_embedding_is_saved(mock_batch, mock_discogs, mock_commons, mock_photos, mock_split,
                                            mock_venue, db):
    """With no ingestion run to finish (and commit) after it, as for `add-event`."""
    async def embed(_db, shows):
        for show in shows:
            show.embedding = b"vector"
    mock_batch.side_effect = embed

    (show,) = await ingest_shows(db, [event_show(_PAGE, _URL)])
    db.rollback()   # what closing the session does to anything not committed

    assert db.get(Show, show.id).embedding == b"vector"


# ── the command ───────────────────────────────────────────────────────────────

@pytest.fixture
def keys_work():
    with patch("app.ingestion.lastfm.lastfm_key_problem", return_value=None), \
         patch("app.ingestion.discogs.discogs_key_problem", return_value=None):
        yield


def _stored(db):
    """`ingest_shows` without the services: it stores the Shows and commits."""
    async def ingest(_db, shows_data, **kwargs):
        shows = upsert_shows(db, shows_data)
        db.commit()
        return shows
    return ingest


@patch("app.cli.SessionLocal")
@patch("app.ingestion.ticketweb.fetch_event", return_value=event_show(_PAGE, _URL))
def test_add_event_adds_the_show(mock_fetch, mock_session, db, keys_work, capsys):
    mock_session.return_value = db
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        main(["add-event", _URL + "?utm_medium=affiliate"])

    mock_fetch.assert_called_once_with(_URL + "?utm_medium=affiliate")
    assert "Teenage Bottlerocket, Brendan Kelly at Moe's Alley, Santa Cruz on Thu Jan 21, 2027" in capsys.readouterr().out
    assert db.query(Show).one().source == "ticketweb"


@patch("app.cli.SessionLocal")
@patch("app.ingestion.ticketweb.fetch_event", return_value=event_show(_PAGE, _URL))
def test_add_event_says_when_the_list_already_has_it(mock_fetch, mock_session, db, keys_work, capsys):
    upsert_shows(db, [_listing()])
    mock_session.return_value = db
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        main(["add-event", _URL])

    assert "the List already has it" in capsys.readouterr().out


@patch("app.ingestion.ticketweb.fetch_event", side_effect=EventError("couldn't fetch it: 506"))
def test_add_event_exits_non_zero_when_the_page_cant_be_read(mock_fetch, keys_work):
    with pytest.raises(SystemExit, match="couldn't fetch it"):
        main(["add-event", _URL])


@patch("app.ingestion.ticketweb.fetch_event")
@patch("app.ingestion.lastfm.lastfm_key_problem", return_value="LASTFM_API_KEY isn't set")
@patch("app.ingestion.discogs.discogs_key_problem", return_value=None)
def test_add_event_needs_the_service_keys(mock_discogs, mock_lastfm, mock_fetch):
    with pytest.raises(SystemExit, match="LASTFM_API_KEY"):
        main(["add-event", _URL])
    mock_fetch.assert_not_called()
