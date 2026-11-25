"""A misspelt Band's name put right (app/ingestion/spelling.py): close names from the services, the likeliest looked
up as a Band; at ingest (app/scheduler.py) and for stored Bands (app/ingestion/respell_bands.py)."""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.ingestion.respell_bands import candidates, respell_stored
from app.ingestion.spelling import Candidate, Respelling, as_listed, close_names, likeliest, respell
from app.ingestion.upsert import find_band, upsert_shows
from app.models.band import Band
from app.models.show import Show
from app.scheduler import _respell as _real_respell
from app.scheduler import ingest_shows

# What Last.fm's search answers for "Sunamo" and "Middrift", with listeners (2026-11-18).
_SUNAMO = [Candidate("Sunami", 174502), Candidate("Senamo", 19469), Candidate("Cunami Flo", 8806),
           Candidate("Sungmo", 1462), Candidate("Sonamó", 927), Candidate("Sunao", 388)]
_MIDDRIFT = [Candidate("Midrift", 598694), Candidate("Midriff", 5533), Candidate("Midrift • Lossless", 41),
             Candidate("Midkraft", 87), Candidate("Sidedrift", 4), Candidate("MaDrift", 10)]


def test_close_names_are_as_many_words_and_alike():
    assert [c.name for c in close_names("Middrift", _MIDDRIFT)] == ["Midrift", "Midriff", "Sidedrift", "MaDrift"]
    assert close_names("Outta Pocket", [Candidate("Pocket Rocket", 9), Candidate("Outta Pocket", 9)]) == []


def test_the_most_listened_to_is_the_likeliest_not_the_closest():
    """"Sunao" (388 listeners) is closer to "Sunamo" than Sunami (174,502) is."""
    assert likeliest("Sunamo", _SUNAMO) == "Sunami"
    assert likeliest("Middrift", _MIDDRIFT) == "Midrift"


def test_without_a_clear_lead_nothing_is_put_right():
    assert likeliest("Sunamo", [Candidate("Sunami", 20000), Candidate("Senamo", 19469)]) is None
    assert likeliest("Sunamo", [Candidate("Sunami", 0)]) is None
    assert likeliest("Sunamo", []) is None


# What Last.fm's search answers for "Time Spent /Driving" (2026-11-25), its first fifteen.
_TIME_SPENT = [Candidate("Time Spent Driving", 29800), Candidate("Time Spent Driving, J Robbins", 11),
               Candidate("Time Spent Driving - Topic", 5), Candidate("Time  Spent Driving", 3),
               Candidate("Time Spent", 645), Candidate("Time Spent Alone", 528), Candidate("Time Well Spent", 206),
               Candidate("Time Spent Burning", 90), Candidate("Time Spent Breathing", 79)]


def test_a_name_that_differs_only_in_punctuation_is_close():
    """Its slug is the listed name's; leaving it out made "Time Spent /Driving" Time Spent Burning."""
    assert likeliest("Time Spent /Driving", _TIME_SPENT) == "Time Spent Driving"


def test_the_listed_name_itself_isnt_a_close_name():
    assert close_names("Sunamo", [Candidate("Sunamo", 9), Candidate("sunamo ", 9)]) == []


def test_one_name_spelt_twice_isnt_its_own_rival():
    assert likeliest("Sunamo", [Candidate("Sunami", 174502), Candidate("SUNAMI", 900)]) == "Sunami"


def test_a_name_put_right_is_written_as_the_listing_writes_names():
    assert as_listed("SUNAMI", "Sunamo") == "Sunami"
    assert as_listed("Midrift", "Middrift") == "Midrift"
    assert as_listed("SUNAMI", "SUNAMO") == "SUNAMI"


def _found(mbid=None):
    return {"genres": [], "mb_genres": False, "mbid": mbid, "links": [], "namesakes": False}


def test_the_likeliest_is_the_bands_name_only_if_a_service_has_it():
    looked_up = []

    def lookup(name):
        looked_up.append(name)
        return _found("mb-sunami" if name == "SUNAMI" else None)

    fixed = respell("Sunamo", lambda _: [Candidate("SUNAMI", 174502), Candidate("Senamo", 19469)], lookup,
                    lambda name, found: None)
    assert fixed == Respelling("Sunami", _found("mb-sunami"), None)   # as the listing writes names
    assert looked_up == ["SUNAMI"]   # the subsequent call, with the name spelt right
    assert respell("Sunamo", lambda _: _SUNAMO, lambda name: _found(), lambda name, found: None) is None


def test_discogs_having_it_is_enough():
    fixed = respell("Middrift", lambda _: _MIDDRIFT, lambda name: _found(), lambda name, found: "discogs artist")
    assert (fixed.name, fixed.discogs) == ("Midrift", "discogs artist")


# ── At ingest ────────────────────────────────────────────────────────────────

def _listing(bands):
    return {"date": date(2026, 12, 26), "bands": bands, "act_notes": [None] * len(bands),
            "band_enrichment": [(b, {"genres": []}) for b in bands], "venue_name": "San Jose Civic",
            "city": "San Jose", "address": "135 San Carlos St, San Jose", "venue_website": None,
            "door_time": "5:30pm", "set_time": None,
            "price_raw": "$35/$40", "age_restriction": "a/a", "status": "upcoming", "source": "list",
            "is_recommended": False, "will_sell_out": False, "is_pit": False, "is_drink_tickets": False,
            "is_no_reentry": False, "is_sold_out": False, "is_matinee": False, "is_benefit": False, "notes": None,
            "raw_text": " ".join(bands)}


def _services(known):
    """MusicBrainz knowing only the names in `known`."""
    return lambda name, use_llm=True: {**_found(f"mb-{name}" if name in known else None), "genres": ["punk"]}


@pytest.fixture
def services():
    with patch("app.scheduler._enrich_venue", return_value={"google_place_id": "ChIJ-civic", "city": "San Jose"}), \
         patch("app.scheduler.split_joint_name", side_effect=lambda name: [name]), \
         patch("app.scheduler.save_band_photos", return_value=0), \
         patch("app.scheduler.commons_photo", return_value=None), \
         patch("app.scheduler.discogs_artist", return_value=None), \
         patch("app.scheduler.lastfm_tags", return_value=[]), \
         patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock), \
         patch("app.scheduler.lastfm_artists", return_value=[("Sunami", 174502), ("Senamo", 19469), ("Sunao", 388)]), \
         patch("app.scheduler._enrich_band", side_effect=_services({"Sunami", "No Pressure"})) as lookup:
        yield lookup


@pytest.fixture
def respelling():
    """The real spelling check, which conftest's no_respelling turns off."""
    with patch("app.scheduler._respell", side_effect=_real_respell):
        yield


async def test_a_misspelt_band_is_stored_spelt_right(db, services, respelling):
    (show,) = await ingest_shows(db, [_listing(["Sunamo", "No Pressure"])])

    assert [a.band.name for a in sorted(show.acts, key=lambda a: a.position)] == ["Sunami", "No Pressure"]
    sunami = db.query(Band).filter(Band.name == "Sunami").one()
    assert (sunami.spellings, sunami.genres) == (["Sunamo"], ["punk"])
    assert db.query(Band).filter(Band.name == "Sunamo").count() == 0
    # Looked up as listed, then with the name spelt right: the subsequent call.
    assert [c.args[0] for c in services.call_args_list] == ["Sunamo", "Sunami", "No Pressure"]


async def test_the_next_listing_misspelt_so_is_the_same_band_without_asking_again(db, services, respelling):
    await ingest_shows(db, [_listing(["Sunamo", "No Pressure"])])
    services.reset_mock()

    (show,) = await ingest_shows(db, [_listing(["Sunamo", "No Pressure"])])

    services.assert_not_called()
    assert [a.band.name for a in show.acts] == ["Sunami", "No Pressure"]
    assert db.query(Band).count() == 2


async def test_a_name_no_service_has_spelt_any_way_stays_as_listed(db, services, respelling):
    services.side_effect = _services({"No Pressure"})   # not Sunami either
    (show,) = await ingest_shows(db, [_listing(["Sunamo", "No Pressure"])])
    assert [a.band.name for a in show.acts] == ["Sunamo", "No Pressure"]
    assert db.query(Band).filter(Band.name == "Sunamo").one().spellings == []


async def test_a_band_a_service_has_as_listed_isnt_respelt(db, services, respelling):
    services.side_effect = _services({"Sunamo", "Sunami", "No Pressure"})
    (show,) = await ingest_shows(db, [_listing(["Sunamo", "No Pressure"])])
    assert [a.band.name for a in show.acts] == ["Sunamo", "No Pressure"]


def test_a_band_is_found_by_a_spelling_it_was_put_right_from(db):
    db.add(Band(name="Sunami", spellings=["Sunamo"]))
    db.flush()
    assert find_band(db, "Sunamo").name == "Sunami"
    assert find_band(db, "SUNAMO").name == "Sunami"
    assert find_band(db, "Sunamos") is None


# ── Stored Bands (respell-bands) ─────────────────────────────────────────────

def _respelt(names):
    return lambda name: Respelling(names[name], _found("mb"), None) if name in names else None


def test_a_stored_misspelt_band_is_renamed_and_looked_up_again(db):
    (show,) = upsert_shows(db, [_listing(["Sunamo", "Middrift", "No Pressure"])])
    bands = candidates(db, ["Sunamo", "Middrift", "No Pressure"])

    done = respell_stored(db, bands, matched=lambda name: name == "No Pressure",
                          respell=_respelt({"Sunamo": "Sunami", "Middrift": "Midrift"}), apply=True)

    assert [str(r) for r in done] == [f"'Sunamo' -> 'Sunami' (band {bands[0][0].id})",
                                      f"'Middrift' -> 'Midrift' (band {bands[1][0].id})"]
    show = db.get(Show, show.id)
    assert [a.band.name for a in sorted(show.acts, key=lambda a: a.position)] == ["Sunami", "Midrift", "No Pressure"]
    sunami = find_band(db, "Sunami")
    assert (sunami.spellings, sunami.enriched_at) == (["Sunamo"], None)   # the backfill looks it up again


def test_a_stored_misspelt_band_is_merged_into_the_band_spelt_right(db):
    upsert_shows(db, [_listing(["Sunamo", "No Pressure"]),
                      {**_listing(["Sunami", "Seltzer"]), "venue_name": "The Ritz"}])
    sunami_id = find_band(db, "Sunami").id
    ((sunamo, _),) = candidates(db, ["Sunamo"])

    (done,) = respell_stored(db, [(sunamo, "Sunamo")], matched=lambda name: False, respell=_respelt({"Sunamo": "Sunami"}),
                             apply=True)

    assert done.merged_into == sunami_id
    assert db.query(Band).filter(Band.name == "Sunamo").count() == 0
    sunami = db.get(Band, sunami_id)
    assert sunami.spellings == ["Sunamo"]
    assert len(sunami.acts) == 2


def test_a_dry_run_changes_nothing(db):
    upsert_shows(db, [_listing(["Sunamo"])])
    db.commit()
    done = respell_stored(db, candidates(db, ["Sunamo"]), matched=lambda name: False,
                          respell=_respelt({"Sunamo": "Sunami"}))
    assert len(done) == 1
    assert find_band(db, "Sunamo").name == "Sunamo"


def test_a_band_put_right_wrongly_is_respelt_from_its_listed_spelling(db):
    upsert_shows(db, [_listing(["Time Spent /Driving"])])
    band = find_band(db, "Time Spent /Driving")
    band.spellings, band.name = ["Time Spent /Driving"], "Time Spent Burning"
    db.flush()

    bands = candidates(db, ["Time Spent /Driving"])
    assert bands == [(band, "Time Spent /Driving")]
    (done,) = respell_stored(db, bands, matched=lambda name: name == "Time Spent Burning",
                             respell=_respelt({"Time Spent /Driving": "Time Spent Driving"}), apply=True)

    assert str(done) == f"'Time Spent /Driving' -> 'Time Spent Driving' (band {band.id})"
    assert (band.name, band.spellings, band.enriched_at) == ("Time Spent Driving", ["Time Spent /Driving"], None)


def test_a_band_already_spelt_right_isnt_marked_again(db):
    db.add(Band(name="Sunami", spellings=["Sunamo"], enriched_at=datetime(2026, 11, 18)))
    db.flush()
    assert respell_stored(db, candidates(db, ["Sunamo"]), matched=lambda name: False,
                          respell=_respelt({"Sunamo": "Sunami"})) == []


def test_without_names_the_bands_on_upcoming_shows_with_nothing_from_the_services(db):
    upsert_shows(db, [_listing(["Sunamo", "No Pressure"]), {**_listing(["Old Band"]), "date": date(2020, 1, 1)}])
    find_band(db, "No Pressure").links = [{"type": "official homepage", "url": "https://nopressure.example"}]
    db.flush()
    with patch("app.ingestion.respell_bands.local_today", return_value=date(2026, 11, 18)):
        assert [(b.name, listed) for b, listed in candidates(db)] == [
            ("Sunamo", "Sunamo")]
