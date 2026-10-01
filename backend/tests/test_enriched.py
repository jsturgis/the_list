"""Tests for filling gaps in a formatted edition from the enriched List export."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.ingestion.edition import edition_shows
from app.ingestion.enriched import merge_enriched

_SAMPLES = Path(__file__).parent.parent.parent / "samples"
_FORMATTED = _SAMPLES / "Bay Area & Santa Cruz Concert Events - September 25, 2026 (v2.0.0 Final).json"
_ENRICHED = _SAMPLES / "San Francisco Area Music List for Friday, September 25th, 2026.enriched.json"


def _event(venue=None, artists=None, details="21+ $20 8pm/9pm", date_="Sep 27, 2026", ticketing=None,
           context=None):
    """A schema v2.0.0 event, as both exports write it."""
    v = {"name": "Bottom of the Hill", "address": "1233 17th St, San Francisco", "region": "San Francisco Venues",
         "url": "https://bottomofthehill.com/"}
    v.update(venue or {})
    return {
        "event_id": "id", "date": date_, "day_of_week": "Sun", "status": "scheduled", "age_restriction": "21+",
        "list_flags": [], "doors_time": None, "show_time": None,
        "ticketing": ticketing or {"price_advance": 20, "price_door": None, "is_free": False, "sold_out": False},
        "event_context": context or {},
        "venue": v,
        "artists": artists if artists is not None else [
            {"name": "Sleep", "role": "headliner", "genre": "Doom", "url": "https://sleep.bandcamp.com/"},
            {"name": "Opener", "role": "support", "genre": "Folk", "url": ""},
        ],
        "raw_details": details,
    }


def _merge(formatted_event, *enriched_events):
    [show] = edition_shows({"events": [formatted_event]})
    merge_enriched([show], list(enriched_events))
    return show


def test_matched_show_gets_the_venue_fields_it_lacks():
    show = _merge(_event(), _event(venue={
        "coordinates": {"lat": 37.765, "lng": -122.396}, "image_url": "https://img.example/bott.jpg",
        "instagram": "@bottomofthehill", "nearest_transit": "22 Fillmore"}))

    assert (show["latitude"], show["longitude"]) == (37.765, -122.396)
    assert show["venue_image_url"] == "https://img.example/bott.jpg"
    assert show["venue_instagram"] == "@bottomofthehill"
    assert show["venue_nearest_transit"] == "22 Fillmore"


def test_matched_show_gets_a_ticket_link_and_special_event():
    show = _merge(_event(), _event(
        ticketing={"price_advance": 20, "ticket_url": "https://www.ticketweb.com/event/sleep-tickets/123"},
        context={"special_event": "Psyched! Fest 2026"}))

    assert show["ticket_url"] == "https://www.ticketweb.com/event/sleep-tickets/123"
    assert show["special_event"] == "Psyched! Fest 2026"


def test_fields_the_formatted_edition_has_are_kept():
    show = _merge(
        _event(venue={"coordinates": {"lat": 1.0, "lng": 2.0}}, context={"special_event": "Fat Wreck 35"}),
        _event(venue={"coordinates": {"lat": 37.765, "lng": -122.396}}, context={"special_event": "Other"}))

    assert (show["latitude"], show["longitude"], show["special_event"]) == (1.0, 2.0, "Fat Wreck 35")


def test_artists_get_images_and_notes_by_name_but_not_links_or_genres():
    show = _merge(_event(), _event(artists=[
        {"name": "opener", "role": "support", "genre": "Pop", "url": "https://wrong.example/",
         "image_url": "https://img.example/opener.jpg", "note": "solo acoustic set"},
        {"name": "Sleep", "role": "headliner", "genre": "Rock", "url": "https://sleep.example/",
         "image_url": "https://img.example/sleep.jpg"},
    ]))

    enrichment = dict(show["band_enrichment"])
    assert enrichment["Sleep"]["image_url"] == "https://img.example/sleep.jpg"
    assert enrichment["Opener"]["image_url"] == "https://img.example/opener.jpg"
    assert enrichment["Sleep"]["genres"] == ["doom"]
    assert enrichment["Sleep"]["bandcamp_url"] == "https://sleep.bandcamp.com/"
    assert enrichment["Opener"]["genres"] == ["folk"] and enrichment["Opener"]["website_url"] is None
    assert dict(zip(show["bands"], show["act_notes"])) == {"Sleep": None, "Opener": "solo acoustic set"}


def test_entries_in_another_schema_are_skipped():
    # The export's last entry is the email footer in an older shape: no artists, an ISO date.
    footer = {"event_id": "footer", "date": "2027-06-19", "artists_raw": "All bands deserve 3 stars",
              "venue_raw": "The Guild Theater", "raw_details": ""}
    show = _merge(_event(), footer, _event(venue={"instagram": "@bottomofthehill"}))

    assert show["venue_instagram"] == "@bottomofthehill"


def _instagram_after_merge(formatted_venue, enriched_venue):
    show = _merge(_event(venue={"name": formatted_venue}),
                  _event(venue={"name": enriched_venue, "instagram": "@venue"}))
    return show["venue_instagram"]


def test_venue_name_variants_match():
    assert _instagram_after_merge("Fox Theater", "the Fox Theatre") == "@venue"
    assert _instagram_after_merge("Brick & Mortar Music Hall", "Brick and Mortar Music Hall") == "@venue"
    assert _instagram_after_merge("HopMonk Tavern (Novato)", "HopMonk Tavern Novato") == "@venue"
    assert _instagram_after_merge("Henry J Kaiser Center", "Henry J. Kaiser Center for the Arts") == "@venue"
    assert _instagram_after_merge("Hotel Utah Saloon", "Hotel Utah") == "@venue"
    assert _instagram_after_merge("Apple Jacks Bar", "Apple Jack's Bar") == "@venue"


def test_different_venue_or_date_does_not_match():
    assert _instagram_after_merge("Fox Theater", "Foxy Lounge") is None
    show = _merge(_event(), _event(date_="Sep 28, 2026", venue={"instagram": "@venue"}))
    assert show["venue_instagram"] is None


def test_two_shows_at_a_venue_on_one_day_are_told_apart_by_door_time():
    matinee, evening = edition_shows({"events": [_event(details="a/a $10 1pm/2pm"), _event(details="21+ $20 8pm/9pm")]})
    merge_enriched([matinee, evening], [
        _event(details="21+ $20 8pm/9pm", ticketing={"ticket_url": "https://tix.example/evening"}),
        _event(details="a/a $10 1pm/2pm", ticketing={"ticket_url": "https://tix.example/matinee"}),
    ])

    assert matinee["ticket_url"] == "https://tix.example/matinee"
    assert evening["ticket_url"] == "https://tix.example/evening"


def test_an_unclear_match_is_left_alone():
    show = _merge(_event(details="21+ $20 8pm/9pm"),
                  _event(details="a/a 1pm/2pm", ticketing={"ticket_url": "https://tix.example/a"}),
                  _event(details="a/a 4pm/5pm", ticketing={"ticket_url": "https://tix.example/b"}))

    assert show["ticket_url"] is None


def test_artist_name_variants_match():
    show = _merge(
        _event(artists=[{"name": "Ilana Glazer", "role": "headliner"}, {"name": "MT Jones", "role": "support"},
                        {"name": "Melvin Seals And JGB", "role": "support"}]),
        _event(artists=[{"name": "Ilana Glazer (comedian)", "image_url": "https://img.example/ilana.jpg"},
                        {"name": "Mt. Jones", "image_url": "https://img.example/mt.jpg"},
                        {"name": "Melvin Seals & JGB", "image_url": "https://img.example/jgb.jpg"}]))

    assert [e["image_url"] for _, e in show["band_enrichment"]] == [
        "https://img.example/ilana.jpg", "https://img.example/mt.jpg", "https://img.example/jgb.jpg"]


# ── the real sample pair ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sample_pair():
    shows = edition_shows(json.loads(_FORMATTED.read_text(encoding="utf-8")))
    before = copy.deepcopy(shows)
    matched = merge_enriched(shows, json.loads(_ENRICHED.read_text(encoding="utf-8")))
    return before, shows, matched


def test_sample_pair_fills_most_shows(sample_pair):
    before, after, matched = sample_pair
    count = lambda shows, field: sum(1 for s in shows if s.get(field) is not None)

    assert matched > 1100 and len(after) == 1210
    assert count(before, "latitude") < 500 < 1100 < count(after, "latitude")
    assert count(before, "venue_image_url") < 400 < 1000 < count(after, "venue_image_url")
    assert count(before, "ticket_url") == 0 and count(after, "ticket_url") > 300
    assert sum(1 for s in after for _, e in s["band_enrichment"] if e["image_url"]) > 350


def test_sample_pair_overwrites_nothing(sample_pair):
    before, after, _ = sample_pair
    for old, new in zip(before, after):
        for field, value in old.items():
            if field == "act_notes":
                assert all(n == m for n, m in zip(value, new[field]) if n)
            elif field == "band_enrichment":
                for (_, e_old), (_, e_new) in zip(value, new[field]):
                    assert all(e_new[k] == v for k, v in e_old.items() if v is not None)
            elif value is not None:
                assert new[field] == value, field
