"""Tests for upsert_shows — uses the in-memory SQLite test DB from conftest."""
from __future__ import annotations

from datetime import date

import pytest

from app.ingestion.upsert import find_venue, region_for_city, upsert_shows
from app.models.act import Act
from app.models.band import Band
from app.models.show import AgeRestriction, Show, ShowStatus
from app.models.venue import Region, Venue


# ── fixtures ──────────────────────────────────────────────────────────────────

def _show(
    *,
    bands: list[str] | None = None,
    venue_name: str = "The Fillmore",
    city: str = "S.F.",
    date_: date = date(2026, 9, 25),
    door_time: str | None = "7pm",
    price_raw: str | None = "$25/$28",
    age_restriction: str | None = "21+",
    status: str = "upcoming",
    **kwargs,
) -> dict:
    return {
        "date": date_,
        "bands": bands if bands is not None else ["Headliner", "Support Act"],
        "venue_name": venue_name,
        "city": city,
        "door_time": door_time,
        "set_time": None,
        "price_raw": price_raw,
        "age_restriction": age_restriction,
        "status": status,
        "is_recommended": False,
        "will_sell_out": False,
        "is_pit": False,
        "is_drink_tickets": False,
        "is_no_reentry": False,
        "ticket_url": None,
        "notes": None,
        "raw_text": "raw",
        "genres": [],
        "spotify_url": None,
        "soundcloud_url": None,
        "venue_website": None,
        "address": None,
        "latitude": None,
        "longitude": None,
        "google_place_id": None,
        **kwargs,
    }


# ── idempotency ───────────────────────────────────────────────────────────────

def test_idempotent_show(db):
    data = [_show()]
    upsert_shows(db, data)
    upsert_shows(db, data)
    assert db.query(Show).count() == 1


def test_idempotent_venue(db):
    data = [_show()]
    upsert_shows(db, data)
    upsert_shows(db, data)
    assert db.query(Venue).count() == 1


def test_idempotent_bands(db):
    data = [_show(bands=["Alpha", "Beta"])]
    upsert_shows(db, data)
    upsert_shows(db, data)
    assert db.query(Band).count() == 2


# ── venue ─────────────────────────────────────────────────────────────────────

def test_venue_city_and_region(db):
    upsert_shows(db, [_show(venue_name="Fox Theater", city="Oakland")])
    v = db.query(Venue).filter(Venue.name == "Fox Theater").one()
    assert v.city == "Oakland"
    assert v.region == Region.east_bay


def test_venue_region_sf(db):
    upsert_shows(db, [_show(city="S.F.")])
    v = db.query(Venue).one()
    assert v.region == Region.sf


def test_venue_region_north_bay(db):
    upsert_shows(db, [_show(venue_name="Phoenix Theater", city="Petaluma")])
    assert db.query(Venue).one().region == Region.north_bay


def test_venue_region_south_bay(db):
    upsert_shows(db, [_show(venue_name="The Ritz", city="San Jose")])
    assert db.query(Venue).one().region == Region.south_bay


def test_venue_region_santa_cruz(db):
    upsert_shows(db, [_show(venue_name="The Catalyst", city="Santa Cruz")])
    assert db.query(Venue).one().region == Region.santa_cruz


def test_venue_region_unknown_defaults_to_sf(db):
    upsert_shows(db, [_show(city="Atlantis")])
    assert db.query(Venue).one().region == Region.sf


def test_venue_website_persisted(db):
    upsert_shows(db, [_show(venue_website="https://thefillmore.com")])
    assert db.query(Venue).one().website_url == "https://thefillmore.com"


def test_a_stored_placeholder_website_is_replaced_or_cleared(db):
    # Earlier editions stored Steve's own site for Venues whose site the producer didn't know.
    upsert_shows(db, [_show(venue_website="https://thefillmore.com")])
    venue = db.query(Venue).one()
    venue.website_url = "https://stevelist.com/"
    upsert_shows(db, [_show(venue_website="https://www.thefillmore.com/")])
    assert venue.website_url == "https://www.thefillmore.com/"

    venue.website_url = "https://stevelist.com/"
    upsert_shows(db, [_show(venue_website=None)])
    assert venue.website_url is None


def test_a_venue_website_is_kept_once_set(db):
    upsert_shows(db, [_show(venue_website="https://thefillmore.com")])
    upsert_shows(db, [_show(venue_website="https://other.example")])
    assert db.query(Venue).one().website_url == "https://thefillmore.com"


def test_venue_google_maps_fields_persisted(db):
    upsert_shows(db, [_show(
        address="1805 Geary Blvd, San Francisco, CA",
        latitude=37.7842,
        longitude=-122.4324,
        google_place_id="ChIJabc123",
    )])
    v = db.query(Venue).one()
    assert v.address == "1805 Geary Blvd, San Francisco, CA"
    assert v.latitude == pytest.approx(37.7842)
    assert v.longitude == pytest.approx(-122.4324)
    assert v.google_place_id == "ChIJabc123"


def test_reuses_existing_venue(db):
    upsert_shows(db, [
        _show(venue_name="Bottom of the Hill", city="S.F.", date_=date(2026, 9, 25)),
        _show(venue_name="Bottom of the Hill", city="S.F.", date_=date(2026, 9, 26)),
    ])
    assert db.query(Venue).count() == 1


def test_reuses_venue_listed_with_and_without_the(db):
    upsert_shows(db, [
        _show(venue_name="the Fox Theater", city="Oakland", date_=date(2026, 10, 1)),
        _show(venue_name="Fox Theater", city="Oakland", date_=date(2026, 10, 2)),
        _show(venue_name="FOX THEATER", city="Oakland", date_=date(2026, 10, 3)),
    ])
    assert db.query(Venue).count() == 1
    assert db.query(Show).count() == 3


# ── price normalisation ───────────────────────────────────────────────────────

def test_price_slash(db):
    upsert_shows(db, [_show(price_raw="$25/$28")])
    s = db.query(Show).one()
    assert s.price_min == pytest.approx(25.0)
    assert s.price_max == pytest.approx(28.0)
    assert s.is_free is False


def test_price_multi_tier(db):
    upsert_shows(db, [_show(price_raw="$25/$27/$30/$35/$40")])
    s = db.query(Show).one()
    assert s.price_min == pytest.approx(25.0)
    assert s.price_max == pytest.approx(40.0)


def test_price_single(db):
    upsert_shows(db, [_show(price_raw="$15")])
    s = db.query(Show).one()
    assert s.price_min == pytest.approx(15.0)
    assert s.price_max == pytest.approx(15.0)


def test_price_free(db):
    upsert_shows(db, [_show(price_raw="free")])
    s = db.query(Show).one()
    assert s.is_free is True
    assert s.price_min == pytest.approx(0.0)
    assert s.price_max == pytest.approx(0.0)


def test_price_missing(db):
    upsert_shows(db, [_show(price_raw=None)])
    s = db.query(Show).one()
    assert s.price_min is None
    assert s.price_max is None
    assert s.is_free is False


# ── age restriction ───────────────────────────────────────────────────────────

def test_age_21_plus(db):
    upsert_shows(db, [_show(age_restriction="21+")])
    assert db.query(Show).one().age_restriction == AgeRestriction.plus_21


def test_age_all_ages(db):
    upsert_shows(db, [_show(age_restriction="a/a")])
    assert db.query(Show).one().age_restriction == AgeRestriction.all_ages


def test_age_unknown(db):
    upsert_shows(db, [_show(age_restriction=None)])
    assert db.query(Show).one().age_restriction == AgeRestriction.unknown


# ── acts / bands ──────────────────────────────────────────────────────────────

def test_acts_positions(db):
    upsert_shows(db, [_show(bands=["Headliner", "Middle", "Opener"])])
    acts = db.query(Act).order_by(Act.position).all()
    assert [a.band.name for a in acts] == ["Headliner", "Middle", "Opener"]
    assert acts[0].position == 0


def test_act_notes_follow_their_band(db):
    # The DJ is dropped, so notes must be matched by name rather than position.
    upsert_shows(db, [_show(bands=["dj Opener", "Black Flag", "Starcrawler"],
                            act_notes=[None, "Greg Ginn, Max Zanelly", None])])
    acts = {a.band.name: a for a in db.query(Act)}
    assert acts["Black Flag"].note == "Greg Ginn, Max Zanelly"
    assert acts["Starcrawler"].note is None


def test_dj_filtered(db):
    upsert_shows(db, [_show(bands=["Real Band", "dj Aaron Axelsen", "Support"])])
    names = [b.name for b in db.query(Band).all()]
    assert "dj Aaron Axelsen" not in names
    assert "Real Band" in names
    assert "Support" in names


def test_b2b_filtered(db):
    upsert_shows(db, [_show(bands=["Real Band", "Act A b2b Act B"])])
    names = [b.name for b in db.query(Band).all()]
    assert "Act A b2b Act B" not in names
    assert "Real Band" in names


def test_lineup_change_replaces_acts(db):
    base = _show(bands=["Old Headliner", "Old Support"])
    upsert_shows(db, [base])
    assert db.query(Act).count() == 2

    updated = {**base, "bands": ["New Headliner"]}
    upsert_shows(db, [updated])
    acts = db.query(Act).all()
    assert len(acts) == 1
    assert acts[0].band.name == "New Headliner"


def test_shared_band_across_shows(db):
    shared = "Rose City Band"
    upsert_shows(db, [
        _show(bands=[shared, "Rain Parade"], date_=date(2026, 9, 25)),
        _show(bands=[shared, "Motrik"], date_=date(2026, 9, 26)),
    ])
    assert db.query(Band).filter(Band.name == shared).count() == 1
    assert db.query(Show).count() == 2


def test_a_new_spelling_of_a_known_band_joins_it(db):
    """Steve writes the same Band differently from week to week: case, punctuation, "&" or "and", accents."""
    upsert_shows(db, [_show(bands=["Swept to Sea", "Brian Mello & The Afterglow"], date_=date(2026, 9, 25))])
    upsert_shows(db, [_show(bands=["Swept To Sea!", "Brian Mello And The Afterglow"], date_=date(2026, 9, 26))])
    assert sorted(b.name for b in db.query(Band).all()) == ["Brian Mello & The Afterglow", "Swept to Sea"]
    assert db.query(Act).count() == 4


def test_two_spellings_of_one_band_in_a_lineup_are_one_act(db):
    upsert_shows(db, [_show(bands=["Da Pupz", "Opener", "Da Pupz!"])])
    show = db.query(Show).one()
    assert [(a.band.name, a.position) for a in show.acts] == [("Da Pupz", 0), ("Opener", 1)]


def test_a_name_of_only_punctuation_matches_only_itself(db):
    upsert_shows(db, [_show(bands=["!!!", "..."])])
    assert sorted(b.name for b in db.query(Band).all()) == ["!!!", "..."]


def test_duplicate_band_on_same_show_keeps_one_act(db):
    """Steve sometimes repeats a headliner in the comma-separated lineup."""
    upsert_shows(db, [_show(bands=["Grant-Lee Phillips", "Grant-Lee Phillips"])])
    acts = db.query(Act).all()
    assert len(acts) == 1
    assert acts[0].band.name == "Grant-Lee Phillips"
    assert acts[0].position == 0
    assert db.query(Band).count() == 1


# ── headliner enrichment ──────────────────────────────────────────────────────

def test_headliner_genres_persisted(db):
    upsert_shows(db, [_show(bands=["Rose City Band", "Rain Parade"], genres=["country rock", "indie"])])
    headliner = db.query(Band).filter(Band.name == "Rose City Band").one()
    support = db.query(Band).filter(Band.name == "Rain Parade").one()
    assert headliner.genres == ["country rock", "indie"]
    assert support.genres == []


def test_headliner_streaming_urls_persisted(db):
    upsert_shows(db, [_show(
        bands=["Beck", "Support"],
        spotify_url="https://open.spotify.com/artist/beck",
        soundcloud_url=None,
    )])
    beck = db.query(Band).filter(Band.name == "Beck").one()
    assert beck.spotify_url == "https://open.spotify.com/artist/beck"


# ── status / flags ────────────────────────────────────────────────────────────

def test_status_cancelled(db):
    upsert_shows(db, [_show(status="cancelled")])
    assert db.query(Show).one().status == ShowStatus.cancelled


def test_flags_persisted(db):
    upsert_shows(db, [_show(
        is_recommended=True, will_sell_out=True,
        is_pit=True, is_drink_tickets=True, is_no_reentry=True,
    )])
    s = db.query(Show).one()
    assert s.is_recommended and s.will_sell_out and s.is_pit
    assert s.is_drink_tickets and s.is_no_reentry


@pytest.mark.parametrize("city, region", [
    ("Santa Cruz", Region.santa_cruz),
    ("Pacifica", Region.sf),  # San Mateo coast, not Santa Cruz
    ("San Francisco", Region.sf),
    ("Napa", Region.north_bay),
    ("Felton", Region.santa_cruz),
    ("Cupertino", Region.south_bay),
    ("Fremont", Region.east_bay),
    ("Vallejo", Region.north_bay),
])
def test_region_for_city(city, region):
    assert region_for_city(city) == region


def test_reuses_venue_with_same_google_place_id(db):
    upsert_shows(db, [
        _show(venue_name="Felton Music Hall", city="Felton", date_=date(2026, 10, 15), google_place_id="ChIJfelton"),
        _show(venue_name="The Felton Music Hall & Bar", city="Felton", date_=date(2026, 10, 23), google_place_id="ChIJfelton"),
    ])
    assert db.query(Venue).count() == 1
    assert db.query(Show).count() == 2


def test_same_name_in_another_region_is_a_different_venue(db):
    upsert_shows(db, [
        _show(venue_name="the Fox Theater", city="Oakland", date_=date(2026, 10, 1), google_place_id="ChIJoakland"),
        _show(venue_name="Fox Theater", city="Redwood City", date_=date(2026, 10, 2), google_place_id="ChIJredwood"),
    ])
    assert db.query(Venue).count() == 2


def test_same_name_in_same_region_is_the_same_venue_even_if_place_id_changes(db):
    # Adding the street to the Places query can return a different place for the same Venue.
    upsert_shows(db, [
        _show(venue_name="Felton Music Hall", city="Felton", date_=date(2026, 10, 1), google_place_id="ChIJbusiness"),
        _show(venue_name="Felton Music Hall", city="Felton", date_=date(2026, 10, 2), google_place_id="ChIJbuilding"),
    ])
    assert db.query(Venue).count() == 1


def test_a_known_variant_name_joins_the_venue_it_is_a_variant_of(db):
    upsert_shows(db, [
        _show(venue_name="Hotel Utah Saloon", city="S.F.", date_=date(2026, 11, 1), google_place_id="ChIJutah"),
        _show(venue_name="Hotel Utan", city="S.F.", date_=date(2026, 11, 8), google_place_id="ChIJutahinn"),
        _show(venue_name="Mabuhay Gardens", city="S.F.", date_=date(2026, 11, 6)),
        _show(venue_name="the On Broadway", city="S.F.", date_=date(2026, 11, 7)),
        _show(venue_name="on Broadway", city="S.F.", date_=date(2026, 11, 22)),
    ])
    assert sorted(v.name for v in db.query(Venue)) == ["Hotel Utah Saloon", "Mabuhay Gardens"]
    assert db.query(Show).count() == 5


def test_a_variant_name_matches_by_name_before_google_place(db):
    # Google places "on Broadway" at Broadway Studios, another Venue.
    upsert_shows(db, [
        _show(venue_name="Broadway Studios", city="S.F.", date_=date(2026, 11, 1), google_place_id="ChIJstudios"),
        _show(venue_name="Mabuhay Gardens", city="S.F.", date_=date(2026, 11, 6), google_place_id="ChIJmabuhay"),
        _show(venue_name="on Broadway", city="S.F.", date_=date(2026, 11, 7), google_place_id="ChIJstudios"),
    ])
    shows = {s.date.day: s.venue.name for s in db.query(Show)}
    assert shows == {1: "Broadway Studios", 6: "Mabuhay Gardens", 7: "Mabuhay Gardens"}


def test_a_new_venue_listed_under_a_variant_name_gets_its_usual_name(db):
    upsert_shows(db, [_show(venue_name="Shed A, Pier 48", city="S.F.")])
    assert db.query(Venue).one().name == "Pier 48"


def _venue(db, name, city, region):
    venue = Venue(name=name, city=city, region=region)
    db.add(venue)
    db.flush()
    return venue


def test_steves_names_for_a_venue_join_it(db):
    """The Venues ingested before the List was read from Steve's page go by tidier names than his."""
    stored = {name: _venue(db, name, city, region) for name, city, region in [
        ("The Castro Theatre", "San Francisco", Region.sf),
        ("The UC Theatre", "Berkeley", Region.east_bay),
        ("Kilowatt Bar", "San Francisco", Region.sf),
        ("Brick & Mortar Music Hall", "San Francisco", Region.sf),
        ("Winter's Tavern", "Pacifica", Region.sf),
        ("The Make-Out Room", "San Francisco", Region.sf),
        ("Henry J Kaiser Center", "Oakland", Region.east_bay),
    ]}
    listed = [("the Castro", "San Francisco", "The Castro Theatre"), ("Castro Theater", "San Francisco", "The Castro Theatre"),
              ("the UC Theater", "Berkeley", "The UC Theatre"), ("the Kilowatt", "San Francisco", "Kilowatt Bar"),
              ("the Brick and Mortar", "San Francisco", "Brick & Mortar Music Hall"),
              ("Winters Tavern", "Pacifica", "Winter's Tavern"), ("Makeout Room", "San Francisco", "The Make-Out Room"),
              ("Henry J. Kaiser Center", "Oakland", "Henry J Kaiser Center")]
    for name, city, usual in listed:
        assert find_venue(db, name, None, (city,)) is stored[usual], name
    upsert_shows(db, [_show(venue_name=name, city=city, date_=date(2026, 11, 1 + i))
                      for i, (name, city, _) in enumerate(listed)])
    assert db.query(Venue).count() == len(stored)


def test_a_name_that_is_a_different_venue_in_each_city(db):
    novato = _venue(db, "HopMonk Tavern (Novato)", "Novato", Region.north_bay)
    sebastopol = _venue(db, "HopMonk Tavern (Sebastopol)", "Sebastopol", Region.north_bay)
    bill_graham = _venue(db, "Bill Graham Civic Auditorium", "San Francisco", Region.sf)
    san_jose = _venue(db, "San Jose Civic Center", "San Jose", Region.south_bay)

    assert find_venue(db, "Hopmonk", None, ("Novato",)) is novato
    assert find_venue(db, "Hopmonk Tavern", None, ("Sebastopol",)) is sebastopol
    assert find_venue(db, "the Civic Auditorium", None, ("San Francisco",)) is bill_graham
    assert find_venue(db, "Civic Auditorium", None, ("San Jose",)) is san_jose
    assert find_venue(db, "Hopmonk", None, ("Petaluma",)) is None   # no Hopmonk we know there


def test_a_typo_in_a_venues_name_still_finds_it(db):
    independent = _venue(db, "The Independent", "San Francisco", Region.sf)
    castro = _venue(db, "The Castro Theatre", "San Francisco", Region.sf)
    ivy_room = _venue(db, "The Ivy Room", "Albany", Region.east_bay)
    _venue(db, "The Ritz", "San Jose", Region.south_bay)

    assert find_venue(db, "the Indpendent", None, ("San Francisco",)) is independent
    assert find_venue(db, "the Ivy Roomm", None, ("Albany",)) is ivy_room
    assert find_venue(db, "the eCastro", None, ("San Francisco",)) is castro   # a typo of his short name for it
    # Not a typo: another name, a short name, or the same name in another Region.
    assert find_venue(db, "the Independence", None, ("San Francisco",)) is None
    assert find_venue(db, "the Rits", None, ("San Jose",)) is None
    assert find_venue(db, "the Indpendent", None, ("San Jose",)) is None


def test_google_neighbourhood_city_does_not_split_a_venue(db):
    # First run: Google reports the neighbourhood; later run: no Google result, listing city only.
    upsert_shows(db, [
        _show(venue_name="Starry Plough", city="Berkeley", place_city="Temescal", date_=date(2026, 10, 1)),
        _show(venue_name="Starry Plough", city="Berkeley", date_=date(2026, 10, 2)),
    ])
    [venue] = db.query(Venue).all()
    assert venue.region == Region.east_bay


# ── a listing whose time changes ──────────────────────────────────────────────

def test_a_listing_with_a_new_door_time_updates_its_show(db):
    upsert_shows(db, [_show(bands=["Pendletons", "Blunt Force Karma"], door_time=None)])
    upsert_shows(db, [_show(bands=["Pendletons", "Blunt Force Karma", "Third Band"], door_time="7pm")])   # time added
    upsert_shows(db, [_show(bands=["The Pendletons"], door_time="7:30pm", date_=date(2026, 9, 26))])     # another day
    upsert_shows(db, [_show(bands=["Pendletons", "Blunt Force Karma", "Third Band"], door_time="8pm")])   # corrected

    first, other_day = db.query(Show).order_by(Show.date).all()
    assert (first.date.day, str(first.door_time), len(first.acts)) == (25, "20:00:00", 3)
    assert other_day.date.day == 26


def test_a_postponed_listing_without_a_time_marks_its_show(db):
    upsert_shows(db, [_show(bands=["Francisca Valenzuela", "Gabi Bravo"], door_time="7pm")])
    upsert_shows(db, [_show(bands=["Francisca Valenzuela", "Gabi Bravo"], door_time=None, status="postponed",
                            price_raw=None, age_restriction=None)])

    show = db.query(Show).one()
    assert (show.status, str(show.door_time)) == (ShowStatus.postponed, "19:00:00")   # keeps the time it had
    upsert_shows(db, [_show(bands=["Francisca Valenzuela", "Gabi Bravo"], door_time=None, status="postponed")])
    assert db.query(Show).count() == 1   # and stays one Show at the next ingest


def test_an_early_and_a_late_show_by_one_headliner_stay_two_shows(db):
    early, late = _show(bands=["Snarky Puppy"], door_time="7pm"), _show(bands=["Snarky Puppy"], door_time="9:30pm")
    upsert_shows(db, [early])
    upsert_shows(db, [late, early])   # the late show is added to the List, above the early one
    upsert_shows(db, [late, early])

    assert sorted(str(s.door_time) for s in db.query(Show)) == ["19:00:00", "21:30:00"]


def test_another_headliner_at_the_venue_that_day_is_another_show(db):
    upsert_shows(db, [_show(bands=["Band A"], door_time="7pm")])
    upsert_shows(db, [_show(bands=["Band B"], door_time="9pm"), _show(bands=["Band C"], door_time=None)])
    assert db.query(Show).count() == 3


def test_a_listing_that_names_no_band_cancels_the_only_show_there_and_keeps_its_lineup(db):
    """"INCORRECT LISTING: dj Raphi at August Hall, S.F.": no Band (DJs aren't), no time."""
    upsert_shows(db, [_show(bands=["Raphi's Band"], venue_name="August Hall", door_time="5pm")])
    upsert_shows(db, [_show(bands=["dj Raphi"], venue_name="August Hall", door_time=None, status="cancelled",
                            notes="incorrect listing")])

    show = db.query(Show).one()
    assert (show.status, show.notes, [a.band.name for a in show.acts]) == (
        ShowStatus.cancelled, "incorrect listing", ["Raphi's Band"])


def test_a_cancelled_listing_that_names_no_band_and_matches_no_show_isnt_stored(db):
    shows = upsert_shows(db, [_show(bands=["dj Raphi"], venue_name="August Hall", door_time=None, status="cancelled")])
    assert shows == [] and db.query(Show).count() == 0
    # An upcoming one is: a DJ night is still a Show at the Venue.
    assert len(upsert_shows(db, [_show(bands=["dj Suzy"], door_time="7pm")])) == 1


# ── fields from the formatted editions ──────────────────────────────────────────────────────

def test_show_extras_are_stored_and_refreshed(db):
    upsert_shows(db, [_show(is_sold_out=False, ticket_provider="ticketweb", is_benefit=True,
                            benefit_cause="food drive", special_event=None, is_matinee=True)])
    upsert_shows(db, [_show(is_sold_out=True, ticket_provider="ticketweb", is_benefit=True,
                            benefit_cause="food drive", special_event=None, is_matinee=True)])
    s = db.query(Show).one()
    assert (s.is_sold_out, s.ticket_provider, s.is_benefit, s.benefit_cause, s.is_matinee) == (
        True, "ticketweb", True, "food drive", True)


def test_a_listing_keeps_what_the_show_already_has_and_the_list_doesnt_say(db):
    """A Show ingested from a formatted edition, then again from Steve's page (app/ingestion/steve_list.py)."""
    upsert_shows(db, [_show(ticket_url="https://tickets.example/1", ticket_provider="ticketweb", is_benefit=True,
                            benefit_cause="food drive", special_event="record release", is_sold_out=True)])
    listing = {k: v for k, v in _show(is_sold_out=False, is_matinee=False, is_benefit=False).items() if k != "ticket_url"}
    upsert_shows(db, [listing])

    s = db.query(Show).one()
    assert (s.ticket_url, s.ticket_provider, s.benefit_cause, s.special_event, s.is_benefit) == (
        "https://tickets.example/1", "ticketweb", "food drive", "record release", True)
    assert s.is_sold_out is False   # the listing says: no longer "(sold out)"


def test_venue_extras_fill_only_empty_fields(db):
    upsert_shows(db, [_show(venue_neighborhood="Mission", venue_type="dive_bar_club", venue_instagram="@one",
                            venue_is_cash_only=True, venue_default_age_restriction="21+")])
    upsert_shows(db, [_show(date_=date(2026, 9, 26), venue_neighborhood="Other", venue_instagram="@two",
                            venue_nearest_transit="16th St BART", venue_is_sober_space=False)])
    v = db.query(Venue).one()
    assert (v.neighborhood, v.venue_type, v.instagram, v.nearest_transit) == ("Mission", "dive_bar_club", "@one", "16th St BART")
    assert (v.is_cash_only, v.is_sober_space, v.default_age_restriction) == (True, False, "21+")


def test_band_extras_fill_only_empty_fields(db):
    upsert_shows(db, [_show(bands=["Sleep"], band_enrichment=[("Sleep", {"image_url": "a.jpg", "website_url": "https://sleep.com", "is_local": False})])])
    upsert_shows(db, [_show(bands=["Sleep"], date_=date(2026, 9, 26), band_enrichment=[("Sleep", {"image_url": "b.jpg", "is_local": True})])])
    b = db.query(Band).one()
    assert (b.image_url, b.website_url, b.is_local) == ("a.jpg", "https://sleep.com", False)
