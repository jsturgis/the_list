"""Tests for embedding helpers, the edition ingestion pipeline, maintenance and venue re-enrichment."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.config import settings
from app.models.band import Band
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.models.show import Show, ShowStatus
from app.models.venue import Region, Venue
from app.pipeline.embed import batch_embed_and_index, embed_and_index_band, embed_and_index_show
from app.clock import local_today
from app.scheduler import _run_ingestion_async, run_daily_maintenance


@pytest.fixture(autouse=True)
def genre_model(no_genre_model):
    """The genre model, judging the tags here outside the vocabulary: "seen live" isn't a genre, the rest are."""
    no_genre_model.side_effect = lambda tag: 0.02 if tag == "seen live" else 0.9
    return no_genre_model


@pytest.fixture(autouse=True)
def offline_musicbrainz():
    """Every new Band is looked up on MusicBrainz at ingest: nobody is found, and no joint billing is split,
    unless a test patches it."""
    with patch("app.scheduler._enrich_band", return_value={"genres": [], "mb_genres": False, "spotify_url": None,
                                                           "soundcloud_url": None, "bandcamp_url": None}), \
         patch("app.scheduler.split_joint_name", side_effect=lambda name: [name]), \
         patch("app.scheduler.save_band_photos", return_value=0), \
         patch("app.scheduler.commons_photo", return_value=None), \
         patch("app.scheduler.lastfm_tags", return_value=[]), \
         patch("app.scheduler.discogs_artist", return_value=None), \
         patch("app.scheduler.discogs_genres", return_value=[]):  # no downloads or lookups unless a test asks
        yield

# ── sample data ───────────────────────────────────────────────────────────────

_FAKE_VEC = np.zeros(768, dtype=np.float32)


# ── embedding helpers ─────────────────────────────────────────────────────────

@patch("app.pipeline.embed.save_index")
@patch("app.pipeline.embed.upsert_vector")
@patch("app.pipeline.embed.load_or_create_index")
@patch("app.pipeline.embed.embed", new_callable=AsyncMock)
async def test_embed_and_index_band_stores_bytes(
    mock_embed, mock_load, mock_upsert, mock_save, db
):
    mock_embed.return_value = _FAKE_VEC
    mock_load.return_value = MagicMock()

    band = Band(name="Deafheaven", genres=["black metal", "shoegaze"])
    db.add(band)
    db.flush()

    await embed_and_index_band(db, band)

    assert band.embedding == _FAKE_VEC.tobytes()
    mock_upsert.assert_called_once()
    mock_save.assert_called_once()


@patch("app.pipeline.embed.save_index")
@patch("app.pipeline.embed.upsert_vector")
@patch("app.pipeline.embed.load_or_create_index")
@patch("app.pipeline.embed.embed", new_callable=AsyncMock)
async def test_embed_and_index_show_stores_bytes(
    mock_embed, mock_load, mock_upsert, mock_save, db
):
    from app.models.act import Act

    mock_embed.return_value = _FAKE_VEC
    mock_load.return_value = MagicMock()

    venue = Venue(name="The Fillmore", city="San Francisco", region=Region.sf)
    db.add(venue)
    db.flush()
    show = Show(date=date(2026, 9, 25), venue_id=venue.id, status=ShowStatus.upcoming)
    db.add(show)
    db.flush()
    band = Band(name="Deafheaven", genres=["black metal"])
    db.add(band)
    db.flush()
    db.add(Act(show_id=show.id, band_id=band.id, position=0))
    db.flush()

    # Reload with relationships
    from sqlalchemy.orm import joinedload
    show = (
        db.query(Show)
        .options(joinedload(Show.venue), joinedload(Show.acts).joinedload(Act.band))
        .filter(Show.id == show.id)
        .one()
    )

    await embed_and_index_show(db, show)

    assert show.embedding == _FAKE_VEC.tobytes()
    mock_upsert.assert_called_once()
    mock_save.assert_called_once()


# ── full pipeline ─────────────────────────────────────────────────────────────

def _edition_event(date_, venue, city, artists, details, age="all_ages"):
    """A schema v2.0.0 event."""
    return {"event_id": f"{date_}-{venue}", "date": date_, "day_of_week": "", "status": "scheduled",
            "age_restriction": age, "list_flags": [], "doors_time": None, "show_time": None, "ticketing": {},
            "venue": {"name": venue, "address": f"1 Main St, {city}", "region": "San Francisco Venues",
                      "url": f"https://{venue.lower().replace(' ', '')}.com/", "coordinates": None},
            "artists": [{"name": n, "role": "headliner" if i == 0 else "support", "genre": g, "url": u}
                        for i, (n, g, u) in enumerate(artists)],
            "raw_details": details}


_EDITION = {
    "title": "Bay Area & Santa Cruz Concert Events", "edition_date": "2026-09-25", "schema_version": "2.0.0",
    "events": [
        _edition_event("Sep 25, 2026", "Bottom of the Hill", "San Francisco",
                       [("Deafheaven", "Blackgaze", "https://deafheaven.bandcamp.com/"), ("Uniform", "Noise Rock", "")],
                       "a/a $15 8pm"),
        _edition_event("Oct 1, 2026", "The Chapel", "San Francisco",
                       [("Mdou Moctar", "Tuareg Rock / Psych", "")], "18+ $25/$28 8pm", age="18+"),
    ],
}
_SAMPLE_FETCH = (_EDITION, {"file_id": "edition-file-id", "file_name": "Concert Events - September 25, 2026.json"})


def _venue_data(name, city, street=None, use_llm=True):
    """Google Places stand-in: a distinct place per Venue."""
    return {"address": f"{street}, {city}, CA, USA", "google_place_id": f"ChIJ-{name}", "city": city}


_NOT_ON_MUSICBRAINZ = {"genres": [], "mb_genres": False, "spotify_url": None, "soundcloud_url": None,
                       "bandcamp_url": None}


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", return_value=_NOT_ON_MUSICBRAINZ)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_imports_the_edition(mock_batch, mock_band, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    assert db.query(Show).count() == 2
    deafheaven = db.query(Band).filter(Band.name == "Deafheaven").one()
    assert deafheaven.genres == ["blackgaze"]
    assert deafheaven.bandcamp_url == "https://deafheaven.bandcamp.com/"
    assert {b.name for b in db.query(Band)} == {"Deafheaven", "Uniform", "Mdou Moctar"}
    chapel = db.query(Venue).filter(Venue.name == "The Chapel").one()
    assert chapel.google_place_id == "ChIJ-The Chapel"
    assert chapel.website_url == "https://thechapel.com/"
    mock_batch.assert_called_once()


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_records_the_ingestion_run(mock_batch, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    run = db.query(IngestionRun).one()
    assert run.status == IngestionStatus.success
    assert run.email_subject == "Bay Area & Santa Cruz Concert Events — Sep 25, 2026"
    assert run.email_message_id == "edition-file-id"
    assert run.email_received_at.date() == date(2026, 9, 25)
    assert (run.shows_parsed, run.shows_upserted, run.shows_new) == (2, 2, 2)


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_idempotent_and_enriches_only_new_venues(mock_batch, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)
    assert mock_venue.call_count == 2
    counts = (db.query(Show).count(), db.query(Band).count(), db.query(Venue).count())

    mock_venue.reset_mock()
    await _run_ingestion_async(db=db)

    assert (db.query(Show).count(), db.query(Band).count(), db.query(Venue).count()) == counts
    mock_venue.assert_not_called()
    assert db.query(IngestionRun).order_by(IngestionRun.id.desc()).first().shows_new == 0


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_makes_no_llm_calls(mock_batch, mock_venue, mock_fetch, db):
    """Edition names are already clean, so venue enrichment runs without the LLM."""
    with patch("app.pipeline.enrichment.get_enrichment_llm") as llm:
        await _run_ingestion_async(db=db)
    llm.assert_not_called()
    assert mock_venue.call_count == 2
    assert all(call.args[3] is False for call in mock_venue.call_args_list)  # use_llm=False


_NO_GENRE_EDITION = {
    **_EDITION,
    "events": _EDITION["events"] + [
        _edition_event("Oct 2, 2026", "Bottom of the Hill", "San Francisco",
                       [("Chat Pile", "", ""), ("Deafheaven", "Blackgaze", ""), ("Mystery Act", "", "")], "21+ $20 9pm"),
        _edition_event("Oct 3, 2026", "The Chapel", "San Francisco", [("Chat Pile", "", "")], "21+ $20 9pm"),
    ],
}


def _musicbrainz(name, use_llm=True):
    found = {
        # MusicBrainz's curated genres
        "Chat Pile": {"genres": ["noise rock", "sludge metal"], "mb_genres": True, "spotify_url": None,
                      "soundcloud_url": None, "bandcamp_url": "https://chatpile.bandcamp.com/"},
        "Deafheaven": {"genres": ["shoegaze", "black metal"], "mb_genres": True,
                       "spotify_url": "https://open.spotify.com/artist/deafheaven", "soundcloud_url": None,
                       "bandcamp_url": "https://deafheavens.bandcamp.com/", "website_url": None,
                       "links": [{"type": "free streaming", "url": "https://open.spotify.com/artist/deafheaven"},
                                 {"type": "social network", "url": "https://www.instagram.com/deafheaven/"}]},
        # Only free-form tags, no curated genres
        "Uniform": {"genres": ["seen live", "noise"], "mb_genres": False, "spotify_url": None,
                    "soundcloud_url": None, "bandcamp_url": None},
    }
    return found.get(name, _NOT_ON_MUSICBRAINZ)


@patch("app.scheduler.fetch_latest_edition", return_value=(_NO_GENRE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_musicbrainz)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_takes_genres_from_musicbrainz_then_the_edition(mock_batch, mock_band, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    genres = {b.name: b.genres for b in db.query(Band)}
    assert genres["Chat Pile"] == ["noise rock", "sludge metal"]  # MusicBrainz; the edition has none
    assert genres["Deafheaven"] == ["shoegaze", "black metal"]   # MusicBrainz over the edition's "Blackgaze"
    assert genres["Mystery Act"] == []                           # in neither
    chat_pile = db.query(Band).filter(Band.name == "Chat Pile").one()
    assert chat_pile.bandcamp_url == "https://chatpile.bandcamp.com/"
    # MusicBrainz's links win over the edition's (deafheaven.bandcamp.com); it adds the ones the edition lacks.
    deafheaven = db.query(Band).filter(Band.name == "Deafheaven").one()
    assert deafheaven.bandcamp_url == "https://deafheavens.bandcamp.com/"
    assert deafheaven.spotify_url == "https://open.spotify.com/artist/deafheaven"
    # Every MusicBrainz link is kept, for the site to group (app/band_links.py).
    assert [link["url"] for link in deafheaven.links] == [
        "https://open.spotify.com/artist/deafheaven", "https://www.instagram.com/deafheaven/"]
    # Every new Band is looked up, once per name, and without the LLM.
    looked_up = sorted(call.args[0] for call in mock_band.call_args_list)
    assert looked_up == ["Chat Pile", "Deafheaven", "Mdou Moctar", "Mystery Act", "Uniform"]
    assert all(call.args[1] is False for call in mock_band.call_args_list)


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_musicbrainz)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_uses_the_editions_genre_only_when_every_service_has_none(mock_batch, mock_band, mock_venue,
                                                                                  mock_fetch, db):
    await _run_ingestion_async(db=db)

    # Uniform has only free-form tags on MusicBrainz: its genres among them still beat the edition's "Noise Rock"
    # ("seen live" isn't a genre, app/ingestion/genre_filter.py).
    assert db.query(Band).filter(Band.name == "Uniform").one().genres == ["noise"]
    # Mdou Moctar isn't on MusicBrainz or Last.fm: only then the edition's genres.
    assert db.query(Band).filter(Band.name == "Mdou Moctar").one().genres == ["tuareg rock", "psych"]


def _musicbrainz_tags_only(name, use_llm=True):
    found = {
        "Chat Pile": {**_NOT_ON_MUSICBRAINZ, "genres": ["seen live"], "mbid": "chat-pile-mbid"},  # tags, no genres
        "Uniform": {**_NOT_ON_MUSICBRAINZ, "genres": ["noise"], "mbid": "uniform-mbid"},
    }
    return found.get(name, _NOT_ON_MUSICBRAINZ)


@patch("app.scheduler.fetch_latest_edition", return_value=(_NO_GENRE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_musicbrainz_tags_only)
@patch("app.scheduler.lastfm_tags", side_effect=lambda name, mbid: {"Chat Pile": ["noise rock", "sludge metal"]}.get(name, []))
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_takes_last_fm_tags_when_musicbrainz_has_no_curated_genres(
        mock_batch, mock_lastfm, mock_band, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    genres = {b.name: b.genres for b in db.query(Band)}
    assert genres["Chat Pile"] == ["noise rock", "sludge metal"]  # Last.fm's, over MusicBrainz's free-form tags
    assert genres["Uniform"] == ["noise"]                         # MusicBrainz's tags, over the edition's
    assert genres["Deafheaven"] == ["blackgaze"]                  # nothing anywhere else: the edition's, last
    assert genres["Mystery Act"] == []                            # nowhere
    # Asked for every Band without curated MusicBrainz genres, once each, with the MusicBrainz id.
    assert sorted(c.args for c in mock_lastfm.call_args_list) == [
        ("Chat Pile", "chat-pile-mbid"), ("Deafheaven", None), ("Mdou Moctar", None), ("Mystery Act", None),
        ("Uniform", "uniform-mbid")]


@patch("app.scheduler.fetch_latest_edition", return_value=(_NO_GENRE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_musicbrainz_tags_only)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_falls_back_to_musicbrainz_tags_when_last_fm_has_none(mock_batch, mock_band, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)  # Last.fm stubbed to nothing by default
    assert db.query(Band).filter(Band.name == "Uniform").one().genres == ["noise"]
    # Only the genres among them: Chat Pile's one tag, "seen live", isn't, and the edition has none.
    assert db.query(Band).filter(Band.name == "Chat Pile").one().genres == []


@patch("app.scheduler.fetch_latest_edition", return_value=(_NO_GENRE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_musicbrainz)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_looks_up_only_bands_new_to_the_database(mock_batch, mock_band, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)
    mock_band.reset_mock()

    await _run_ingestion_async(db=db)

    # Both Bands are saved now: Mystery Act still has no genre, but it was looked up once already.
    mock_band.assert_not_called()
    assert db.query(Band).filter(Band.name == "Mystery Act").one().genres == []


_JOINT_EDITION = {
    **_EDITION,
    "events": [
        _edition_event("Oct 5, 2026", "The Ritz", "San Jose",
                       [("Dying Fetus And Sanguisugabogg", "Death Metal", ""), ("Belle and Sebastian", "Indie Pop", "")],
                       "a/a $32 7pm"),
    ],
}


def _joint(name):
    return {"Dying Fetus And Sanguisugabogg": ["Dying Fetus", "Sanguisugabogg"]}.get(name, [name])


@patch("app.scheduler.fetch_latest_edition", return_value=(_JOINT_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.split_joint_name", side_effect=_joint)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_splits_joint_billings_into_two_bands(mock_batch, mock_split, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    show = db.query(Show).one()
    lineup = [(a.position, a.band.name) for a in sorted(show.acts, key=lambda a: a.position)]
    assert lineup == [(0, "Dying Fetus"), (1, "Sanguisugabogg"), (2, "Belle and Sebastian")]
    assert db.query(Band).filter(Band.name == "Sanguisugabogg").one().genres == ["death metal"]
    # Only names that could be joint billings are checked; a second ingest checks nothing new.
    assert sorted(c.args[0] for c in mock_split.call_args_list) == ["Belle and Sebastian", "Dying Fetus And Sanguisugabogg"]
    mock_split.reset_mock()
    await _run_ingestion_async(db=db)
    assert [c.args[0] for c in mock_split.call_args_list] == ["Dying Fetus And Sanguisugabogg"]


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_records_how_the_new_bands_came_out(mock_batch, mock_venue, mock_fetch, db):
    # No service knows anyone (the offline defaults), so every new Band falls back to the edition.
    await _run_ingestion_async(db=db)

    run = db.query(IngestionRun).order_by(IngestionRun.id.desc()).first()
    assert (run.new_bands, run.new_bands_without_photo_pct, run.new_bands_photo_from_edition_pct) == (3, 100.0, 0.0)
    assert run.new_bands_genres_from_edition_pct == 100.0   # Deafheaven, Uniform, Mdou Moctar: the edition's genres
    assert run.new_bands_links_from_edition_pct == 33.3     # Deafheaven's Bandcamp link

    await _run_ingestion_async(db=db)  # the same edition again: no new Bands
    run = db.query(IngestionRun).order_by(IngestionRun.id.desc()).first()
    assert (run.new_bands, run.new_bands_without_photo_pct, run.new_bands_genres_from_edition_pct) == (0, None, None)


_TWO_DATES_EDITION = {
    **_EDITION,
    "events": [
        _edition_event("Oct 2, 2026", "Bottom of the Hill", "San Francisco",
                       [("Local Heroes", "Rock", "https://localheroes.bandcamp.com/")], "21+ $12 8pm"),
        _edition_event("Oct 3, 2026", "The Chapel", "San Francisco",
                       [("Local Heroes", "Punk", "https://localheroes.example/")], "21+ $12 8pm"),
    ],
}


@patch("app.scheduler.fetch_latest_edition", return_value=(_TWO_DATES_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_the_edition_fallback_stats_count_a_band_on_several_shows(mock_batch, mock_venue, mock_fetch, db):
    """The Band keeps its first Show's edition genres and each link field's first value; the stats must agree."""
    await _run_ingestion_async(db=db)

    heroes = db.query(Band).filter(Band.name == "Local Heroes").one()
    assert heroes.genres == ["rock"] and heroes.bandcamp_url == "https://localheroes.bandcamp.com/"
    run = db.query(IngestionRun).order_by(IngestionRun.id.desc()).first()
    assert (run.new_bands, run.new_bands_genres_from_edition_pct, run.new_bands_links_from_edition_pct) == (1, 100.0, 100.0)


def _discogs_artists(name, links):
    from app.ingestion.discogs import DiscogsArtist
    ids = {"Chat Pile": 7258502, "Uniform": 11, "Mdou Moctar": 12}
    return DiscogsArtist(ids[name], name, f"https://www.discogs.com/artist/{ids[name]}") if name in ids else None


@patch("app.scheduler.fetch_latest_edition", return_value=(_NO_GENRE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_musicbrainz_tags_only)
@patch("app.scheduler.lastfm_tags", side_effect=lambda name, mbid: {"Mdou Moctar": ["tuareg rock"]}.get(name, []))
@patch("app.scheduler.discogs_artist", side_effect=_discogs_artists)
@patch("app.scheduler.discogs_genres", side_effect=lambda artist_id: {7258502: ["sludge metal", "noise rock"]}.get(artist_id, []))
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_takes_discogs_genres_after_last_fm_and_before_musicbrainz_tags(
        mock_batch, mock_genres, mock_artist, mock_lastfm, mock_band, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    genres = {b.name: b.genres for b in db.query(Band)}
    assert genres["Chat Pile"] == ["sludge metal", "noise rock"]  # Discogs', over MusicBrainz's "seen live"
    assert genres["Mdou Moctar"] == ["tuareg rock"]              # Last.fm's: Discogs isn't asked for genres
    assert genres["Uniform"] == ["noise"]                        # Discogs has none: MusicBrainz's free-form tags
    assert genres["Deafheaven"] == ["blackgaze"]                 # not on any service: the edition's, last
    asked = sorted(c.args[0] for c in mock_genres.call_args_list)
    assert asked == [11, 7258502]                                # Bands with a Discogs artist and no Last.fm tags
    # Every new Band's Discogs artist is looked up once; a second ingest looks up no one.
    assert sorted(c.args[0] for c in mock_artist.call_args_list) == [
        "Chat Pile", "Deafheaven", "Mdou Moctar", "Mystery Act", "Uniform"]
    mock_artist.reset_mock()
    await _run_ingestion_async(db=db)
    mock_artist.assert_not_called()


def _discogs_with_members(name, links):
    from app.ingestion.discogs import DiscogsArtist
    if name != "Deafheaven":
        return None
    return DiscogsArtist(1, "Deafheaven", "https://www.discogs.com/artist/1", members=[
        {"name": "George Clarke", "active": True}, {"name": "Derek Prine", "active": False}])


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.discogs_artist", side_effect=_discogs_with_members)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_saves_a_new_bands_members_from_discogs(mock_batch, mock_discogs, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    assert db.query(Band).filter(Band.name == "Deafheaven").one().members == [
        {"name": "George Clarke", "active": True}, {"name": "Derek Prine", "active": False}]
    assert db.query(Band).filter(Band.name == "Uniform").one().members == []   # not on Discogs
    # Saved once: a later ingest doesn't touch them.
    mock_discogs.side_effect = lambda name, links: None
    await _run_ingestion_async(db=db)
    assert len(db.query(Band).filter(Band.name == "Deafheaven").one().members) == 2


@patch("app.scheduler.fetch_latest_edition", return_value=(None, None))
async def test_pipeline_returns_early_when_no_edition(mock_fetch, db):
    await _run_ingestion_async(db=db)
    assert db.query(Show).count() == 0
    assert db.query(IngestionRun).one().status == IngestionStatus.no_email


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", return_value={})
@patch("app.pipeline.embed.save_index")
@patch("app.pipeline.embed.upsert_vector")
@patch("app.pipeline.embed.load_or_create_index")
@patch("app.pipeline.embed.embed", new_callable=AsyncMock)
async def test_faiss_indices_saved(
    mock_embed, mock_load, mock_upsert_v, mock_save, mock_venue, mock_fetch, db
):
    mock_embed.return_value = _FAKE_VEC
    mock_load.return_value = MagicMock()

    await _run_ingestion_async(db=db)

    assert mock_save.call_count == 2  # exactly one save per index type


# ── daily maintenance ─────────────────────────────────────────────────────────

def _seed_show(db, show_date, status=ShowStatus.upcoming):
    v = db.query(Venue).first()
    if not v:
        v = Venue(name="Test Venue", city="SF", region=Region.sf)
        db.add(v)
        db.flush()
    s = Show(date=show_date, venue_id=v.id, status=status)
    db.add(s)
    db.flush()
    return s


def test_maintenance_marks_past_shows(db):
    today = local_today()
    _seed_show(db, today - timedelta(days=1), ShowStatus.upcoming)
    _seed_show(db, today + timedelta(days=1), ShowStatus.upcoming)
    db.commit()

    run_daily_maintenance(db=db)

    db.expire_all()
    statuses = {s.date: s.status for s in db.query(Show).all()}
    assert statuses[today - timedelta(days=1)] == ShowStatus.past
    assert statuses[today + timedelta(days=1)] == ShowStatus.upcoming


def test_maintenance_hard_deletes_old_shows(db):
    today = local_today()
    old_date = today - timedelta(days=settings.data_retention_days + 1)
    recent_date = today - timedelta(days=1)
    _seed_show(db, old_date, ShowStatus.past)
    _seed_show(db, recent_date, ShowStatus.upcoming)
    db.commit()

    run_daily_maintenance(db=db)

    db.expire_all()
    dates = [s.date for s in db.query(Show).all()]
    assert old_date not in dates
    assert recent_date in dates


# ── startIngestion mutation ───────────────────────────────────────────────────

@patch("app.graphql.mutations.asyncio.create_task")
def test_start_ingestion_mutation(mock_create_task, client):
    resp = client.post("/graphql", json={"query": "mutation { startIngestion }"})
    assert resp.status_code == 200
    body = resp.json()
    assert "errors" not in body
    assert body["data"]["startIngestion"] == "ingestion started"
    mock_create_task.assert_called_once()


# ── venue re-enrichment ───────────────────────────────────────────────────────

async def test_venue_enrichment_keeps_region_when_google_returns_a_neighbourhood(db):
    from app.scheduler import _run_venue_enrichment_async

    venue = Venue(name="Starry Plough", city="Berkeley", region=Region.east_bay)
    db.add(venue)
    db.commit()
    venue_id = venue.id  # the function closes its session, detaching `venue`
    enrich = MagicMock(return_value={"address": "3101 Shattuck Ave", "city": "Temescal"})

    with patch("app.scheduler.SessionLocal", return_value=db), \
         patch("app.scheduler._enrich_venue", enrich), \
         patch("app.scheduler._clean_venue_name", MagicMock()):
        await _run_venue_enrichment_async(venue_id)

    refreshed = db.get(Venue, venue_id)
    assert refreshed.city == "Temescal"
    assert refreshed.region == Region.east_bay  # not moved to the "sf" default


_IMAGE_EDITION = {
    **_EDITION,
    "events": [{**_EDITION["events"][0],
                "venue": {**_EDITION["events"][0]["venue"], "image_url": "https://example.com/made-up-venue.jpg"},
                "artists": [{**_EDITION["events"][0]["artists"][0], "image_url": "https://example.com/wrong-path.jpg"},
                            _EDITION["events"][0]["artists"][1]]}],
}


@patch("app.scheduler.fetch_latest_edition", return_value=(_IMAGE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.check_image_urls", return_value={
    "https://example.com/made-up-venue.jpg": None,
    "https://example.com/wrong-path.jpg": "https://example.com/real-path.jpg",
})
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_saves_only_images_that_load(mock_batch, mock_images, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    assert db.query(Band).filter(Band.name == "Deafheaven").one().image_url == "https://example.com/real-path.jpg"
    assert db.query(Venue).filter(Venue.name == "Bottom of the Hill").one().image_url is None
    assert sorted(mock_images.call_args.args[0]) == ["https://example.com/made-up-venue.jpg", "https://example.com/wrong-path.jpg"]


def _photo_client(routes):
    """httpx.Client stand-in for the photo downloads: canned responses by URL, 404 otherwise."""
    import httpx

    real = httpx.Client
    return lambda **kw: real(transport=httpx.MockTransport(lambda req: routes.get(str(req.url), httpx.Response(404))))


def _jpeg_bytes():
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1200, 800), (40, 90, 160)).save(buf, "JPEG")
    return buf.getvalue()


@patch("app.scheduler.fetch_latest_edition", return_value=(_IMAGE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.check_image_urls", side_effect=lambda urls: {u: u for u in urls})
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_saves_band_photos_with_the_data(mock_batch, mock_images, mock_venue, mock_fetch, db, tmp_path,
                                                        monkeypatch):
    import httpx

    from app.ingestion import band_photos
    monkeypatch.setattr(settings, "images_path", str(tmp_path))
    monkeypatch.setattr(band_photos.httpx, "Client", _photo_client(
        {"https://example.com/wrong-path.jpg": httpx.Response(200, content=_jpeg_bytes())}))

    with patch("app.scheduler.save_band_photos", band_photos.save_band_photos):
        await _run_ingestion_async(db=db)

    deafheaven = db.query(Band).filter(Band.name == "Deafheaven").one()
    assert deafheaven.image_url.startswith(f"bands/{deafheaven.id}-") and deafheaven.image_url.endswith(".webp")
    assert (tmp_path / deafheaven.image_url).is_file()
    # The Venue's photo isn't downloaded: only Band photos are kept with the data.
    assert db.query(Venue).filter(Venue.name == "Bottom of the Hill").one().image_url == "https://example.com/made-up-venue.jpg"


@patch("app.scheduler.fetch_latest_edition", return_value=(_IMAGE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.check_image_urls", side_effect=lambda urls: {u: u for u in urls})
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_drops_a_band_photo_that_cannot_be_downloaded(mock_batch, mock_images, mock_venue, mock_fetch,
                                                                     db, tmp_path, monkeypatch):
    from app.ingestion import band_photos
    monkeypatch.setattr(settings, "images_path", str(tmp_path))
    monkeypatch.setattr(band_photos.httpx, "Client", _photo_client({}))  # every download 404s

    with patch("app.scheduler.save_band_photos", band_photos.save_band_photos):
        await _run_ingestion_async(db=db)

    assert db.query(Band).filter(Band.name == "Deafheaven").one().image_url is None
    assert not any(tmp_path.rglob("*.webp"))


_COMMONS_CREDIT = {"author": "S. Bollmann", "license": "CC BY-SA 4.0",
                   "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
                   "source_url": "https://commons.wikimedia.org/wiki/File:Deafheaven.jpg"}


def _deafheaven_on_musicbrainz(name, use_llm=True):
    if name != "Deafheaven":
        return _NOT_ON_MUSICBRAINZ
    return {**_NOT_ON_MUSICBRAINZ, "links": [{"type": "wikidata", "url": "https://www.wikidata.org/wiki/Q1"}]}


def _commons(links):
    from app.ingestion.wikimedia import CommonsPhoto
    if any(link["type"] == "wikidata" for link in links):
        return CommonsPhoto("https://upload.wikimedia.org/deafheaven-800.jpg", _COMMONS_CREDIT)
    return None


@patch("app.scheduler.fetch_latest_edition", return_value=(_IMAGE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_deafheaven_on_musicbrainz)
@patch("app.scheduler.commons_photo", side_effect=_commons)
@patch("app.scheduler.check_image_urls", side_effect=lambda urls: {u: u for u in urls})
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_prefers_the_commons_photo_and_saves_its_credit(mock_batch, mock_images, mock_commons, mock_band,
                                                                       mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    deafheaven = db.query(Band).filter(Band.name == "Deafheaven").one()
    assert deafheaven.image_url == "https://upload.wikimedia.org/deafheaven-800.jpg"   # over the edition's
    assert deafheaven.image_credit == _COMMONS_CREDIT
    # A Band already in the database isn't looked up again.
    mock_commons.reset_mock()
    await _run_ingestion_async(db=db)
    mock_commons.assert_not_called()


@patch("app.scheduler.fetch_latest_edition", return_value=(_IMAGE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_deafheaven_on_musicbrainz)
@patch("app.scheduler.commons_photo", side_effect=_commons)
@patch("app.scheduler.check_image_urls", side_effect=lambda urls: {
    u: (None if "upload.wikimedia.org/deafheaven" in u else u) for u in urls})
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_falls_back_to_the_editions_photo_when_the_commons_one_does_not_load(
        mock_batch, mock_images, mock_commons, mock_band, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    deafheaven = db.query(Band).filter(Band.name == "Deafheaven").one()
    assert deafheaven.image_url == "https://example.com/wrong-path.jpg"   # the edition's
    assert deafheaven.image_credit is None                                # which has no credit


@patch("app.scheduler.fetch_latest_edition", return_value=(_IMAGE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.check_image_urls", side_effect=lambda urls: {u: u for u in urls})
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_keeps_the_editions_photo_without_a_credit_when_commons_has_none(
        mock_batch, mock_images, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    deafheaven = db.query(Band).filter(Band.name == "Deafheaven").one()
    assert (deafheaven.image_url, deafheaven.image_credit) == ("https://example.com/wrong-path.jpg", None)


def _deafheaven_on_discogs(name, links):
    from app.ingestion.discogs import DiscogsArtist
    if name != "Deafheaven":
        return None
    return DiscogsArtist(9, "Deafheaven", "https://www.discogs.com/artist/9-Deafheaven",
                         image_url="https://i.discogs.com/deafheaven.jpg")


_DISCOGS_CREDIT = {"source": "Discogs", "author": None, "license": None, "license_url": None,
                   "source_url": "https://www.discogs.com/artist/9-Deafheaven"}


@patch("app.scheduler.fetch_latest_edition", return_value=(_IMAGE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.discogs_artist", side_effect=_deafheaven_on_discogs)
@patch("app.scheduler.check_image_urls", side_effect=lambda urls: {u: u for u in urls})
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_uses_the_discogs_photo_when_commons_has_none(mock_batch, mock_images, mock_discogs, mock_venue,
                                                                     mock_fetch, db):
    await _run_ingestion_async(db=db)

    deafheaven = db.query(Band).filter(Band.name == "Deafheaven").one()
    assert deafheaven.image_url == "https://i.discogs.com/deafheaven.jpg"   # over the edition's
    assert deafheaven.image_credit == _DISCOGS_CREDIT


@patch("app.scheduler.fetch_latest_edition", return_value=(_IMAGE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_deafheaven_on_musicbrainz)
@patch("app.scheduler.commons_photo", side_effect=_commons)
@patch("app.scheduler.discogs_artist", side_effect=_deafheaven_on_discogs)
@patch("app.scheduler.check_image_urls", side_effect=lambda urls: {
    u: (None if "upload.wikimedia.org" in u else u) for u in urls})
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_uses_the_discogs_photo_when_the_commons_one_does_not_load(
        mock_batch, mock_images, mock_discogs, mock_commons, mock_band, mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    deafheaven = db.query(Band).filter(Band.name == "Deafheaven").one()
    assert (deafheaven.image_url, deafheaven.image_credit) == ("https://i.discogs.com/deafheaven.jpg", _DISCOGS_CREDIT)


@patch("app.scheduler.fetch_latest_edition", return_value=(_IMAGE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_deafheaven_on_musicbrainz)
@patch("app.scheduler.commons_photo", side_effect=_commons)
@patch("app.scheduler.discogs_artist", side_effect=_deafheaven_on_discogs)
@patch("app.scheduler.check_image_urls", side_effect=lambda urls: {u: u for u in urls})
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_prefers_commons_to_discogs(mock_batch, mock_images, mock_discogs, mock_commons, mock_band,
                                                   mock_venue, mock_fetch, db):
    await _run_ingestion_async(db=db)

    deafheaven = db.query(Band).filter(Band.name == "Deafheaven").one()
    assert deafheaven.image_url == "https://upload.wikimedia.org/deafheaven-800.jpg"
    assert deafheaven.image_credit == _COMMONS_CREDIT


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_skips_broken_links(mock_batch, mock_venue, mock_fetch, db, no_link_checks):
    broken = {"https://bottomofthehill.com/", "https://deafheaven.bandcamp.com/"}
    no_link_checks.side_effect = lambda urls: {url: url not in broken for url in urls}

    await _run_ingestion_async(db=db)

    assert db.query(Venue).filter(Venue.name == "Bottom of the Hill").one().website_url is None
    assert db.query(Venue).filter(Venue.name == "The Chapel").one().website_url == "https://thechapel.com/"
    assert db.query(Band).filter(Band.name == "Deafheaven").one().bandcamp_url is None


@patch("app.scheduler.fetch_latest_edition", return_value=_SAMPLE_FETCH)
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_checks_only_links_it_would_save(mock_batch, mock_venue, mock_fetch, db, no_link_checks):
    await _run_ingestion_async(db=db)
    assert sorted(no_link_checks.call_args.args[0]) == [
        "https://bottomofthehill.com/", "https://deafheaven.bandcamp.com/", "https://thechapel.com/"]
    no_link_checks.reset_mock()

    await _run_ingestion_async(db=db)

    # Every link is saved now, so nothing is checked again.
    no_link_checks.assert_not_called()


@patch("app.scheduler.fetch_latest_edition", return_value=(_NO_GENRE_EDITION, _SAMPLE_FETCH[1]))
@patch("app.scheduler._enrich_venue", side_effect=_venue_data)
@patch("app.scheduler._enrich_band", side_effect=_musicbrainz_tags_only)
@patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock)
async def test_pipeline_keeps_tags_unfiltered_when_the_genre_model_is_down(
        mock_batch, mock_band, mock_venue, mock_fetch, db, genre_model):
    genre_model.side_effect = None
    genre_model.return_value = None          # Ollama can't be reached
    await _run_ingestion_async(db=db)        # the ingest still runs
    assert db.query(Band).filter(Band.name == "Chat Pile").one().genres == ["seen live"]  # kept, for a recheck
