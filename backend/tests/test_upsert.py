"""Tests for upsert_shows — uses the in-memory SQLite test DB from conftest."""
from __future__ import annotations

from datetime import date

import pytest

from app.ingestion.upsert import region_for_city, upsert_shows
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


def test_google_neighbourhood_city_does_not_split_a_venue(db):
    # First run: Google reports the neighbourhood; later run: no Google result, listing city only.
    upsert_shows(db, [
        _show(venue_name="Starry Plough", city="Berkeley", place_city="Temescal", date_=date(2026, 10, 1)),
        _show(venue_name="Starry Plough", city="Berkeley", date_=date(2026, 10, 2)),
    ])
    [venue] = db.query(Venue).all()
    assert venue.region == Region.east_bay


# ── extra edition fields ──────────────────────────────────────────────────────

def test_show_extras_are_stored_and_refreshed(db):
    upsert_shows(db, [_show(is_sold_out=False, ticket_provider="ticketweb", is_benefit=True,
                            benefit_cause="food drive", special_event=None, is_matinee=True)])
    upsert_shows(db, [_show(is_sold_out=True, ticket_provider="ticketweb", is_benefit=True,
                            benefit_cause="food drive", special_event=None, is_matinee=True)])
    s = db.query(Show).one()
    assert (s.is_sold_out, s.ticket_provider, s.is_benefit, s.benefit_cause, s.is_matinee) == (
        True, "ticketweb", True, "food drive", True)


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
