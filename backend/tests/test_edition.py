"""Tests for importing a formatted edition of Steve's list (structured JSON)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.ingestion.edition import edition_meta, edition_shows

_SAMPLE = Path(__file__).parent.parent.parent / "samples" / (
    "Bay Area & Santa Cruz Concert Events - September 25, 2026 (v2.0.0 Final).json"
)


def _doc(*events, **meta):
    return {"title": "Bay Area & Santa Cruz Concert Events", "edition_date": "2026-09-25",
            "events": list(events), **meta}


def _event(details="a/a $15 7pm/8pm", status="scheduled", artists=None, venue=None, date_="Sep 27, 2026",
           region="Santa Cruz & South Bay Area", age="all_ages", flags=None, doors=None, show=None, ticketing=None):
    """A schema v2.0.0 event."""
    v = {"name": "The Catalyst", "address": "1011 Pacific Ave, Santa Cruz", "url": "https://catalystclub.com/",
         "coordinates": {"lat": 36.9715, "lng": -122.0255}}
    v.update(venue or {})
    v["region"] = region
    return {
        "event_id": "id", "date": date_, "day_of_week": "Sun", "status": status, "age_restriction": age,
        "list_flags": flags or [], "doors_time": doors, "show_time": show,
        "ticketing": ticketing or {"price_advance": None, "price_door": None, "is_free": False, "sold_out": False},
        "venue": v,
        "artists": artists if artists is not None else [
            {"name": "Sleep", "role": "headliner", "genre": "Stoner Doom / Metal", "url": "https://sleep.bandcamp.com/"},
        ],
        "raw_details": details,
    }


# ── the real sample ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sample():
    return json.loads(_SAMPLE.read_text(encoding="utf-8"))


def test_sample_imports_every_event(sample):
    shows = edition_shows(sample)
    assert len(shows) == sample["total_events"] == 1210
    assert all(s["date"] and s["bands"] and s["venue_name"] for s in shows)
    assert {s["status"] for s in shows} == {"upcoming", "cancelled", "postponed"}


def test_sample_has_no_legend_or_footer_text(sample):
    for s in edition_shows(sample):
        blob = json.dumps({k: v for k, v in s.items() if k != "raw_text"}, default=str)
        assert "All bands deserve" not in blob and "Radio Shows" not in blob


def test_sample_last_event_details_are_cut_at_the_legend(sample):
    last = edition_shows(sample)[-1]
    assert (last["date"], last["venue_name"]) == (date(2027, 6, 19), "Guild Theatre")
    assert (last["age_restriction"], last["door_time"], last["set_time"]) == ("a/a", "7pm", "8pm")
    assert last["notes"] is None


# ── mapping ───────────────────────────────────────────────────────────────────

def test_details_become_age_price_times_and_flags():
    [s] = edition_shows(_doc(_event(details="16+ $58.15 7pm/8pm * $ @ ^ #", age="16+")))
    assert (s["age_restriction"], s["price_raw"], s["door_time"], s["set_time"]) == ("16+", "$58.15", "7pm", "8pm")
    assert all(s[f] for f in ("is_recommended", "will_sell_out", "is_pit", "is_drink_tickets", "is_no_reentry"))


def test_parenthesised_details_and_artist_notes_become_show_notes():
    artists = [{"name": "Rusty Chains", "genre": "Country", "url": "", "note": "tribute"},
               {"name": "Opener", "genre": "Folk", "url": ""}]
    [s] = edition_shows(_doc(_event(details="a/a $15 6:30pm/7pm @ (Gilman Benefit)", artists=artists, flags=["@"])))
    assert s["notes"] == "Gilman Benefit; Rusty Chains: tribute"
    assert s["is_pit"]


def test_status_mapping():
    shows = edition_shows(_doc(_event(status="scheduled"), _event(status="cancelled"),
                               _event(status="postponed"), _event(status="something-new")))
    assert [s["status"] for s in shows] == ["upcoming", "cancelled", "postponed", "upcoming"]


def test_venue_name_city_address_and_website():
    [s] = edition_shows(_doc(_event()))
    assert (s["venue_name"], s["city"]) == ("The Catalyst", "Santa Cruz")
    assert s["address"] == "1011 Pacific Ave, Santa Cruz"
    assert s["venue_website"] == "https://catalystclub.com/"


def test_city_falls_back_to_region_for_san_francisco_venues():
    venue = {"name": "The Chapel", "address": "", "url": "", "coordinates": None}
    [s] = edition_shows(_doc(_event(venue=venue, region="San Francisco Venues")))
    assert s["city"] == "San Francisco"


def test_bands_in_order_with_genres_and_streaming_links():
    artists = [
        {"name": "Headliner", "genre": "Indie Rock / Alternative", "url": "https://open.spotify.com/artist/x"},
        {"name": "Second", "genre": "Lo-Fi, Bedroom Pop", "url": "https://soundcloud.com/second"},
        {"name": "Third", "genre": "Hardcore", "url": "https://third.bandcamp.com/"},
        {"name": "Fourth", "genre": "", "url": "https://fourth-band.com/"},
    ]
    [s] = edition_shows(_doc(_event(artists=artists)))
    assert s["bands"] == ["Headliner", "Second", "Third", "Fourth"]
    enrichment = dict(s["band_enrichment"])
    assert enrichment["Headliner"] == {"genres": ["indie rock", "alternative"],
                                       "spotify_url": "https://open.spotify.com/artist/x",
                                       "soundcloud_url": None, "bandcamp_url": None,
                                       "website_url": None, "image_url": None, "is_local": None}
    assert enrichment["Second"]["genres"] == ["lo-fi", "bedroom pop"]
    assert enrichment["Second"]["soundcloud_url"] == "https://soundcloud.com/second"
    assert enrichment["Third"]["bandcamp_url"] == "https://third.bandcamp.com/"
    assert enrichment["Fourth"] == {"genres": [], "spotify_url": None, "soundcloud_url": None, "bandcamp_url": None,
                                    "website_url": "https://fourth-band.com/", "image_url": None, "is_local": None}


def test_edition_meta():
    meta = edition_meta(_doc())
    assert meta == {"subject": "Bay Area & Santa Cruz Concert Events — Sep 25, 2026",
                    "edition_date": date(2026, 9, 25)}


def test_single_part_address_is_the_city():
    venue = {"name": "Siesta Valley Bowl", "address": "Orinda", "url": "", "coordinates": None}
    [s] = edition_shows(_doc(_event(venue=venue, region="East Bay Venues")))
    assert (s["venue_name"], s["city"], s["address"]) == ("Siesta Valley Bowl", "Orinda", None)


def test_unsplit_venue_listing_is_parsed_like_the_email():
    venue = {"name": "Point San Pablo Harbor, 1900 Stenmark Drive, Richmond a/a $44.52 6pm",
             "address": "San Francisco Bay Area", "url": "", "coordinates": None}
    [s] = edition_shows(_doc(_event(venue=venue, details="", age="unspecified", region="East Bay Venues")))
    assert (s["venue_name"], s["city"]) == ("Point San Pablo Harbor", "Richmond")
    assert s["address"] == "1900 Stenmark Drive, Richmond"
    assert (s["age_restriction"], s["price_raw"], s["door_time"]) == ("a/a", "$44.52", "6pm")


def test_details_win_over_values_parsed_from_an_unsplit_venue():
    venue = {"name": "Gray Area, S.F. 21+ $30.49/$36.59 8pm", "address": "San Francisco Bay Area", "url": "", "coordinates": None}
    [s] = edition_shows(_doc(_event(venue=venue, details="18+ $40 9pm", age="unspecified", region="San Francisco Venues")))
    assert (s["venue_name"], s["city"]) == ("Gray Area", "S.F.")
    assert (s["age_restriction"], s["price_raw"], s["door_time"]) == ("18+", "$40", "9pm")


def test_placeholder_address_is_not_stored():
    venue = {"name": "San Francisco Bay Area", "address": "San Francisco Bay Area", "url": "", "coordinates": None}
    [s] = edition_shows(_doc(_event(venue=venue, region="San Francisco Venues")))
    assert s["address"] is None and s["city"] == "San Francisco"


def test_every_sample_show_has_a_city(sample):
    assert [s["venue_name"] for s in edition_shows(sample) if not s["city"]] == []


# ── schema v2.0.0 fields ──────────────────────────────────────────────────────

def test_flags_map_symbols_to_steves_legend_not_the_producer_labels():
    # Steve's legend: * pick, $ will sell out, @ pit, ^ drink tickets, # no re-entry.
    [s] = edition_shows(_doc(_event(details="21+ $20 8pm", flags=["$", "@", "#"])))
    assert (s["will_sell_out"], s["is_pit"], s["is_no_reentry"]) == (True, True, True)
    assert (s["is_recommended"], s["is_drink_tickets"]) == (False, False)


def test_age_restriction_field_wins_and_maps_to_our_values():
    shows = edition_shows(_doc(_event(details="16+ $10 8pm", age="all_ages"), _event(details="$10 8pm", age="13+"),
                               _event(details="18+ $10 8pm", age="unspecified")))
    assert [s["age_restriction"] for s in shows] == ["a/a", "13+", "18+"]


def test_single_time_in_details_is_the_door_time_even_when_structured_says_show_time():
    # Keeps Show identity (date, Venue, door time) consistent with existing data.
    [s] = edition_shows(_doc(_event(details="a/a $15 8pm", doors=None, show="20:00")))
    assert (s["door_time"], s["set_time"]) == ("8pm", None)


def test_structured_times_and_ticketing_fill_gaps_in_details():
    ticketing = {"price_advance": 25.0, "price_door": 30.0, "is_free": False, "sold_out": False}
    [s] = edition_shows(_doc(_event(details="a/a", doors="19:30", show="20:15", ticketing=ticketing)))
    assert (s["door_time"], s["set_time"], s["price_raw"]) == ("7:30pm", "8:15pm", "$25/$30")
    [free] = edition_shows(_doc(_event(details="a/a", ticketing={"is_free": True})))
    assert free["price_raw"] == "free"


def test_venue_coordinates_are_kept():
    [s] = edition_shows(_doc(_event()))
    assert (s["latitude"], s["longitude"]) == (36.9715, -122.0255)


def test_headliner_role_comes_first():
    artists = [{"name": "Opener", "role": "support", "genre": "", "url": ""},
               {"name": "Star", "role": "headliner", "genre": "", "url": ""}]
    [s] = edition_shows(_doc(_event(artists=artists)))
    assert s["bands"] == ["Star", "Opener"]


def test_sample_statuses_and_ages(sample):
    shows = edition_shows(sample)
    assert sum(s["status"] == "cancelled" for s in shows) == 1 and sum(s["status"] == "postponed" for s in shows) == 1
    assert {"13+", "8+"} <= {s["age_restriction"] for s in shows}


def test_venue_description_is_used_when_present():
    [with_desc] = edition_shows(_doc(_event(venue={"description": "  Santa Cruz's long-running rock club.  "})))
    [without] = edition_shows(_doc(_event()))
    assert with_desc["venue_description"] == "Santa Cruz's long-running rock club."
    assert without["venue_description"] is None


# ── extra v2 fields (stored for the frontend) ─────────────────────────────────

def test_show_extras_from_ticketing_context_and_matinee():
    ev = _event(ticketing={"price_advance": 20, "price_door": 25, "is_free": False, "sold_out": True,
                           "provider": "ticketweb"})
    ev.update(is_matinee=True, event_context={"is_benefit": True, "benefit_cause": "canned food drive",
                                              "special_event": "Hardly Strictly Bluegrass"})
    [s] = edition_shows(_doc(ev))
    assert (s["is_matinee"], s["is_sold_out"], s["ticket_provider"]) == (True, True, "ticketweb")
    assert (s["is_benefit"], s["benefit_cause"], s["special_event"]) == (True, "canned food drive", "Hardly Strictly Bluegrass")


def test_show_extras_default_when_missing():
    [s] = edition_shows(_doc(_event()))
    assert (s["is_matinee"], s["is_sold_out"], s["ticket_provider"]) == (False, False, None)
    assert (s["is_benefit"], s["benefit_cause"], s["special_event"]) == (False, None, None)


def test_venue_extras():
    venue = {"neighborhood": "Downtown Santa Cruz", "venue_type": "independent_music_hall",
             "nearest_transit": "Santa Cruz Metro Center (2 min walk)", "instagram": "@catalystclub",
             "image_url": "https://example.com/catalyst.jpg",
             "rules": {"default_age_restriction": "varies", "sober_space": False, "cash_only": True,
                       "membership_required": False}}
    [s] = edition_shows(_doc(_event(venue=venue)))
    assert s["venue_neighborhood"] == "Downtown Santa Cruz"
    assert s["venue_type"] == "independent_music_hall"
    assert s["venue_nearest_transit"] == "Santa Cruz Metro Center (2 min walk)"
    assert (s["venue_instagram"], s["venue_image_url"]) == ("@catalystclub", "https://example.com/catalyst.jpg")
    assert (s["venue_default_age_restriction"], s["venue_is_sober_space"], s["venue_is_cash_only"],
            s["venue_membership_required"]) == ("varies", False, True, False)


def test_band_extras_image_local_and_website():
    artists = [{"name": "Sleep", "role": "headliner", "genre": "Doom", "url": "https://thirdmanrecords.com/pages/sleep",
                "image_url": "https://example.com/sleep.jpg", "is_local": False},
               {"name": "Locals", "role": "support", "genre": "Punk", "url": "https://locals.bandcamp.com/", "is_local": True}]
    [s] = edition_shows(_doc(_event(artists=artists)))
    e = dict(s["band_enrichment"])
    assert (e["Sleep"]["website_url"], e["Sleep"]["image_url"], e["Sleep"]["is_local"]) == (
        "https://thirdmanrecords.com/pages/sleep", "https://example.com/sleep.jpg", False)
    assert (e["Locals"]["website_url"], e["Locals"]["bandcamp_url"], e["Locals"]["is_local"]) == (
        None, "https://locals.bandcamp.com/", True)
