"""Tests for the check of Google Places results against the listed Venue (app/ingestion/venue_check.py).

The results are what Places answered on 2026-11-13 for the List's new Venue names and some awkward ones, in the shape
pipeline.enrichment._enrich_venue returns.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.ingestion.venue_check import (
    ADDRESS_ONLY, CONFIRMED, NOT_CHECKED, NOT_FOUND, UNCONFIRMED, check_venue, checked_details, same_name)
from app.models.venue import Region, Venue
from app.scheduler import ingest_shows

_VENUE = ["establishment", "point_of_interest"]


def _found(google_name, address, city, types=_VENUE, results=1, **extra):
    return {"google_name": google_name, "address": address, "city": city, "google_types": types,
            "google_results": results, "google_place_id": f"ChIJ-{google_name}", "latitude": 37.8,
            "longitude": -122.3, "timezone": "America/Los_Angeles", "phone": "(510) 555-0100",
            "website_url": "https://example.com/", "google_rating": 4.5, **extra}


@pytest.mark.parametrize("name, city, street, found", [
    ("the Big Easy", "Petaluma", "128 American Alley",
     _found("The Big Easy", "128 American Alley, Petaluma, CA 94952, USA", "Petaluma")),
    ("Temescal Arts Center", "Oakland", "511 48th St. at Telegraph",       # "Arts" for Google's "Art"
     _found("Temescal Art Center", "511 48th St, Oakland, CA 94609, USA", "Oakland")),
    ("the Booksmith", "San Francisco", "1727 Haight Street",
     _found("Booksmith", "1727 Haight St, San Francisco, CA 94117, USA", "San Francisco")),
    ("Rio Nido Roadhouse", "Rio Nido", "14540 Canyon 2 Road",              # Google files it under Guerneville
     _found("Rio Nido Roadhouse", "14540 Canyon 2 Rd, Rio Nido, CA 95471, USA", "Guerneville")),
    ("the Fox Theater", "Redwood City", "2215 Broadwa",
     _found("Fox Theatre", "2215 Broadway, Redwood City, CA 94063, USA", "Redwood City")),
    ("Alameda County Fair", "Pleasanton", None,                            # the fair, at its fairgrounds
     _found("Alameda County Fairgrounds", "2005 Valley Ave Gate 8, Pleasanton, CA 94566, USA", "Pleasanton")),
    ("the Arena", "Oakland", None,                                         # Steve's short name
     _found("Oakland Arena", "7000 S Coliseum Wy, Oakland, CA 94621, USA", "Oakland")),
    ("the Indpendent", "San Francisco", None,                              # his typo
     _found("The Independent", "628 Divisadero St, San Francisco, CA 94117, USA", "San Francisco")),
    ("Music Hall", "Felton", None,
     _found("Felton Music Hall", "6275 Hwy 9, Felton, CA 95018, USA", "Felton")),
    ("Streetlight Records", "San Jose", None,
     _found("Streetlight Records", "980 S Bascom Ave, San Jose, CA 95128, USA", "San Jose")),
])
def test_the_venue_google_found_is_confirmed(name, city, street, found):
    check = check_venue(name, city, street, found)
    assert check.status == CONFIRMED, check.reason
    assert checked_details(found, check) is found   # every detail is kept


@pytest.mark.parametrize("name, city, street, found, why", [
    ("the Castro", "San Francisco", None,
     _found("The Castro", "The Castro, San Francisco, CA 94114, USA", "San Francisco",
            types=["neighborhood", "political"]), "an area"),
    ("First Church of the Buzzard", "Oakland", None,
     _found("First Congregational Church of Oakland", "2501 Harrison St, Oakland, CA 94612, USA", "Oakland"),
     "best match is"),
    ("a house", "San Francisco", None,
     _found("The OA House", "1001 Vallejo St, San Francisco, CA 94133, USA", "San Francisco", results=20),
     "20 guesses"),
    ("Zzyzx Flurble Hall", "Berkeley", None,
     _found("Wheeler Hall Auditorium", "Wheeler Hall, Berkeley, CA 94720, USA", "Berkeley", results=20),
     "20 guesses"),
    ("the Giants Ballpark", "San Francisco", None,                         # a nickname: an alias's job
     _found("Oracle Park", "24 Willie Mays Plaza, San Francisco, CA 94107, USA", "San Francisco"), "best match is"),
    ("FML Studios", "Oakland", None,                                       # an address, and not the listed one
     _found("2400 Filbert St", "2400 Filbert St, Oakland, CA 94607, USA", "Oakland",
            types=["premise", "street_address"]), "an address"),
    ("Hopmonk", "Petaluma", None,                                          # the right name in the wrong city
     _found("HopMonk Tavern", "224 Vintage Way, Novato, CA 94945, USA", "Novato"), "isn't in Petaluma"),
    ("the Mystic", "Petaluma", None,                                       # a street named after the city
     _found("Mystic Lounge", "1 Petaluma Blvd N, Sebastopol, CA 95472, USA", "Sebastopol"), "isn't in Petaluma"),
])
def test_a_place_that_isnt_the_venue_is_unconfirmed(name, city, street, found, why):
    check = check_venue(name, city, street, found)
    assert check.status == UNCONFIRMED
    assert why in check.reason
    assert checked_details(found, check) == {}   # nothing of it is stored: no place id to join another Venue by


def test_the_listed_street_address_alone_keeps_only_the_address():
    found = _found("2400 Filbert St", "2400 Filbert St, Oakland, CA 94607, USA", "Oakland",
                   types=["premise", "street_address"])
    check = check_venue("FML Studios", "Oakland", "2400 Filbert Street", found)

    assert check.status == ADDRESS_ONLY
    assert checked_details(found, check) == {
        "address": "2400 Filbert St, Oakland, CA 94607, USA", "city": "Oakland", "latitude": 37.8,
        "longitude": -122.3, "timezone": "America/Los_Angeles"}   # no place id, phone, website or rating


def test_no_result_and_a_result_without_a_name():
    assert check_venue("the Pussy Palace", "Oakland", None, {}).status == NOT_FOUND
    assert checked_details({}, check_venue("the Pussy Palace", "Oakland", None, {})) == {}
    legacy = {"address": "1 Main St, Oakland", "google_place_id": "ChIJ1"}   # no name asked for
    assert check_venue("Somewhere", "Oakland", None, legacy).status == NOT_CHECKED


def test_several_results_confirm_only_the_very_name():
    found = _found("The Ritz", "400 S 1st St, San Jose, CA 95113, USA", "San Jose", results=3)
    assert check_venue("the Ritz", "San Jose", None, found).status == CONFIRMED


@pytest.mark.parametrize("listed, google, same", [
    ("the Arena", "Oakland Arena", True),
    ("Temescal Arts Center", "Temescal Art Center", True),
    ("Brick and Mortar", "Brick & Mortar Music Hall", True),
    ("Winters Tavern", "Winter's Tavern", True),
    ("the Indpendent", "The Independent", True),
    ("the Chapel", "Chapel of the Chimes", True),   # every listed word is in Google's: a known limit of the rule
    ("Bottom of the Hill", "The Hill", True),
    ("Neck of the Woods", "Woods Bar & Brewery", False),
    ("First Church of the Buzzard", "First Congregational Church of Oakland", False),
    ("the Giants Ballpark", "Oracle Park", False),
    ("the Rits", "The Ritz", False),   # too short to allow a typo
])
def test_same_name(listed, google, same):
    assert same_name(listed, google) is same


# ── At ingest ────────────────────────────────────────────────────────────────
# A listing whose city is wrong ("924 Gilman Street, S.F.") joins the stored Venue at the place Google found.

def _listing(venue_name, city):
    return {"date": date(2027, 1, 17), "bands": ["Field Of Flames"], "act_notes": [None],
            "band_enrichment": [("Field Of Flames", {"genres": []})], "venue_name": venue_name, "city": city,
            "address": None, "venue_website": None, "door_time": "7pm", "set_time": "7:30pm",
            "price_raw": "$15/$20", "age_restriction": "a/a", "status": "upcoming", "source": "list",
            "is_recommended": False, "will_sell_out": False, "is_pit": True, "is_drink_tickets": False,
            "is_no_reentry": False, "is_sold_out": False, "is_matinee": False, "is_benefit": False, "notes": None,
            "raw_text": "jan 17 sun Field Of Flames"}


@pytest.fixture
def services():
    with patch("app.scheduler.split_joint_name", side_effect=lambda name: [name]), \
         patch("app.scheduler.save_band_photos", return_value=0), \
         patch("app.scheduler.commons_photo", return_value=None), \
         patch("app.scheduler.discogs_artist", return_value=None), \
         patch("app.scheduler.lastfm_tags", return_value=[]), \
         patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock), \
         patch("app.scheduler._enrich_band", return_value={"genres": [], "mb_genres": False, "mbid": None,
                                                           "links": [], "namesakes": False}):
        yield


def _stored(db, name, city, region, place_id):
    venue = Venue(name=name, city=city, region=region, google_place_id=place_id)
    db.add(venue)
    db.flush()
    return venue


async def test_a_listing_in_the_wrong_city_joins_the_venue_google_found(db, services):
    gilman = _stored(db, "924 Gilman Street", "Berkeley", Region.east_bay, "ChIJ-924 Gilman St")
    found = _found("924 Gilman St", "924 Gilman St, Berkeley, CA 94710, USA", "Berkeley")
    with patch("app.scheduler._enrich_venue", return_value=found):
        (show,) = await ingest_shows(db, [_listing("924 Gilman Street", "San Francisco")])
    assert show.venue_id == gilman.id
    assert db.query(Venue).count() == 1


async def test_a_name_only_like_the_stored_venues_isnt_joined_to_it(db, services):
    """"Hopmonk" in Petaluma can be another Venue than HopMonk Tavern (Novato), the place Google found."""
    novato = _stored(db, "HopMonk Tavern (Novato)", "Novato", Region.north_bay, "ChIJ-HopMonk Tavern")
    found = _found("HopMonk Tavern", "224 Vintage Way, Novato, CA 94945, USA", "Novato")
    with patch("app.scheduler._enrich_venue", return_value=found):
        (show,) = await ingest_shows(db, [_listing("Hopmonk", "Petaluma")])
    assert show.venue_id != novato.id
    assert show.venue.google_place_id is None
