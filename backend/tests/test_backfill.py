"""Tests for backfilling existing Bands with what new ones get at ingest."""
from __future__ import annotations

import io
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from PIL import Image

from app.clock import local_today
from app.ingestion import backfill
from app.ingestion.backfill import pending_bands, recheck_genres, run_backfill
from app.ingestion.band_photos import is_stored
from app.ingestion.discogs import DiscogsArtist
from app.ingestion.wikimedia import CommonsPhoto
from app.models.act import Act
from app.models.band import Band
from app.models.genre_tag import GenreTag
from app.models.show import Show
from app.models.venue import Region, Venue

_RealClient = httpx.Client
_COMMONS = CommonsPhoto("https://upload.wikimedia.org/soulfly-800.jpg", {
    "source": "Wikimedia Commons", "author": "S. Bollmann", "license": "CC BY-SA 4.0", "license_url": None,
    "source_url": "https://commons.wikimedia.org/wiki/File:Soulfly.jpg"})


def _jpeg(color=(30, 60, 90)):
    buf = io.BytesIO()
    Image.new("RGB", (1000, 600), color).save(buf, "JPEG")
    return buf.getvalue()


def _not_on_musicbrainz(name, use_llm=True):
    return {"genres": [], "mb_genres": False, "mbid": None, "spotify_url": None, "soundcloud_url": None,
            "bandcamp_url": None, "website_url": None, "links": []}


@pytest.fixture
def services(tmp_path, monkeypatch):
    """Every service stubbed to know nothing, photo downloads answered from `routes`, embedding stubbed."""
    routes: dict[str, httpx.Response] = {}
    monkeypatch.setattr(backfill.httpx, "Client", lambda **kw: _RealClient(
        transport=httpx.MockTransport(lambda r: routes.get(str(r.url), httpx.Response(404)))))
    with patch.object(backfill, "_enrich_band", side_effect=_not_on_musicbrainz) as mb, \
         patch.object(backfill, "commons_photo", return_value=None) as commons, \
         patch.object(backfill, "discogs_artist", return_value=None) as discogs, \
         patch.object(backfill, "lastfm_tags", return_value=[]) as lastfm, \
         patch.object(backfill, "discogs_genres", return_value=[]) as discogs_genres, \
         patch.object(backfill, "embed_and_index_band", new_callable=AsyncMock) as embed:
        yield type("Services", (), dict(mb=mb, commons=commons, discogs=discogs, lastfm=lastfm,
                                        discogs_genres=discogs_genres, embed=embed, routes=routes,
                                        images=tmp_path))


def _band(db, name, **kw):
    band = Band(name=name, genres=kw.pop("genres", []), **kw)
    db.add(band)
    db.flush()
    return band


def _upcoming_show(db, *bands):
    venue = db.query(Venue).first() or Venue(name="The Ritz", city="San Jose", region=Region.south_bay)
    show = Show(date=local_today() + timedelta(days=3), venue=venue)
    db.add(show)
    db.flush()
    for position, band in enumerate(bands):
        db.add(Act(show_id=show.id, band_id=band.id, position=position))
    db.flush()


async def _run(db, services, **kw):
    return await run_backfill(db, images_dir=services.images, **kw)


def test_bands_on_upcoming_shows_come_first_and_looked_up_ones_are_skipped(db):
    old, playing, done = _band(db, "Old"), _band(db, "Playing"), _band(db, "Done", enriched_at=datetime(2026, 10, 1))
    _upcoming_show(db, playing)
    db.commit()
    assert [b.name for b in pending_bands(db)] == ["Playing", "Old"]


async def test_service_data_wins_and_the_bands_own_is_the_fallback(db, services):
    soulfly = _band(db, "Soulfly", genres=["soul", "funk"], bandcamp_url="https://soulfly.bandcamp.com/",
                    website_url="https://edition.example/")
    keeps = _band(db, "Local Heroes", genres=["punk"], website_url="https://localheroes.example/")
    db.commit()
    services.mb.side_effect = lambda name, use_llm=True: (
        {**_not_on_musicbrainz(name), "genres": ["groove metal", "nu metal"], "mb_genres": True, "mbid": "m",
         "spotify_url": "https://open.spotify.com/artist/s", "website_url": "https://www.soulfly.com",
         "links": [{"type": "free streaming", "url": "https://open.spotify.com/artist/s"}]}
        if name == "Soulfly" else _not_on_musicbrainz(name))
    services.discogs.side_effect = lambda name, links: (
        DiscogsArtist(1, "Soulfly", "https://www.discogs.com/artist/1", members=[{"name": "Max Cavalera", "active": True}])
        if name == "Soulfly" else None)

    result = await _run(db, services)

    db.refresh(soulfly), db.refresh(keeps)
    assert soulfly.genres == ["groove metal", "nu metal"]                    # MusicBrainz over the edition's
    assert soulfly.spotify_url == "https://open.spotify.com/artist/s"
    assert soulfly.website_url == "https://www.soulfly.com"                   # MusicBrainz's over the edition's
    assert soulfly.bandcamp_url == "https://soulfly.bandcamp.com/"            # kept: MusicBrainz has none
    assert soulfly.links == [{"type": "free streaming", "url": "https://open.spotify.com/artist/s"}]
    assert soulfly.members == [{"name": "Max Cavalera", "active": True}]
    assert keeps.genres == ["punk"] and keeps.website_url == "https://localheroes.example/"  # nothing found: kept
    assert soulfly.enriched_at is not None and keeps.enriched_at is not None
    assert result["looked_up"] == 2 and result["remaining"] == 0
    services.embed.assert_awaited_once()                                      # only Soulfly's genres changed


async def test_a_commons_photo_replaces_the_old_stored_one(db, services):
    old = services.images / "bands" / "1-old.webp"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    soulfly = _band(db, "Soulfly", image_url="bands/1-old.webp")
    db.commit()
    services.commons.return_value = _COMMONS
    services.routes[_COMMONS.url] = httpx.Response(200, content=_jpeg())

    await _run(db, services)

    db.refresh(soulfly)
    assert is_stored(soulfly.image_url) and soulfly.image_url != "bands/1-old.webp"
    assert soulfly.image_credit == _COMMONS.credit
    assert not old.exists()


async def test_a_new_photo_gets_its_focal_point_and_a_failed_one_keeps_the_old(db, services):
    replaced = _band(db, "Soulfly", image_url="bands/1-old.webp", image_focus={"x": 10.0, "y": 20.0})
    kept = _band(db, "Kept", image_url="bands/2-old.webp", image_focus={"x": 30.0, "y": 40.0})
    db.commit()
    services.mb.side_effect = lambda name, use_llm=True: {**_not_on_musicbrainz(name), "links": [{"type": "x", "url": name}]}
    # Soulfly's Commons photo downloads (a plain one: no face); Kept's is gone, so it keeps what it had.
    services.routes[_COMMONS.url] = httpx.Response(200, content=_jpeg())
    services.commons.side_effect = lambda links: _COMMONS if links[0]["url"] == "Soulfly" else CommonsPhoto(
        "https://upload.wikimedia.org/gone.jpg", _COMMONS.credit)

    await _run(db, services)

    db.refresh(replaced), db.refresh(kept)
    assert replaced.image_url != "bands/1-old.webp" and replaced.image_focus == {"x": 50.0, "y": 35.0}
    assert kept.image_url == "bands/2-old.webp" and kept.image_focus == {"x": 30.0, "y": 40.0}


async def test_when_every_service_photo_fails_the_band_keeps_its_photo(db, services):
    soulfly = _band(db, "Soulfly", image_url="https://edition.example/soulfly.jpg")
    db.commit()
    services.commons.return_value = _COMMONS                                  # 404: gone
    services.discogs.return_value = DiscogsArtist(1, "Soulfly", "https://www.discogs.com/artist/1",
                                                  image_url="https://i.discogs.com/x.jpg")  # 404 too
    services.routes["https://edition.example/soulfly.jpg"] = httpx.Response(200, content=_jpeg((5, 5, 5)))

    await _run(db, services)

    db.refresh(soulfly)
    assert is_stored(soulfly.image_url)       # the edition's photo, now kept with the data
    assert soulfly.image_credit is None


async def test_the_time_budget_and_the_limit_stop_the_run_and_the_next_run_resumes(db, services):
    for name in ("A", "B", "C"):
        _band(db, name)
    db.commit()

    first = await _run(db, services, limit=2)
    assert (first["looked_up"], first["remaining"]) == (2, 1)
    assert (await _run(db, services, max_minutes=0))["looked_up"] == 0   # out of time before the first Band
    second = await _run(db, services)
    assert (second["looked_up"], second["remaining"]) == (1, 0)


async def test_one_bands_failure_doesnt_stop_the_run(db, services):
    _band(db, "Broken"), _band(db, "Fine")
    db.commit()
    services.mb.side_effect = lambda name, use_llm=True: (_ for _ in ()).throw(RuntimeError("boom")) if name == "Broken" \
        else _not_on_musicbrainz(name)

    result = await _run(db, services)

    assert result["looked_up"] == 1 and result["failed"] == 1
    assert db.query(Band).filter(Band.name == "Broken").one().enriched_at is None   # tried again next run


async def test_a_photo_that_cant_be_downloaded_right_now_is_tried_again_next_run(db, services):
    soulfly = _band(db, "Soulfly", image_url="https://edition.example/soulfly.jpg")
    db.commit()
    services.commons.return_value = _COMMONS
    services.routes[_COMMONS.url] = httpx.Response(503)

    result = await _run(db, services)

    db.refresh(soulfly)
    assert soulfly.image_url == "https://edition.example/soulfly.jpg" and soulfly.image_credit is None
    assert soulfly.enriched_at is None and result["remaining"] == 1


async def test_a_failed_band_keeps_its_old_photo_file_and_the_new_one_is_removed(db, services):
    old = services.images / "bands" / "1-old.webp"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    soulfly = _band(db, "Soulfly", image_url="bands/1-old.webp")
    db.commit()
    services.mb.side_effect = lambda name, use_llm=True: {**_not_on_musicbrainz(name), "genres": ["metal"], "mb_genres": True}
    services.commons.return_value = _COMMONS
    services.routes[_COMMONS.url] = httpx.Response(200, content=_jpeg())
    services.embed.side_effect = RuntimeError("ollama is down")

    result = await _run(db, services)

    db.refresh(soulfly)
    assert result["failed"] == 1 and soulfly.image_url == "bands/1-old.webp" and old.exists()
    assert [p.name for p in old.parent.iterdir()] == ["1-old.webp"]


async def test_tags_that_arent_genres_are_left_out(db, services, no_genre_model):
    _band(db, "Cross Checked", genres=["hardcore"])
    db.commit()
    services.lastfm.return_value = ["youth crew", "seen live", "united states"]
    no_genre_model.side_effect = lambda tag: {"youth crew": 0.8, "seen live": 0.02, "united states": 0.03}[tag]

    await _run(db, services)

    assert db.query(Band).one().genres == ["youth crew"]
    assert db.query(GenreTag).count() == 3                 # each judged once, for next time


def test_recheck_marks_bands_with_tags_that_arent_genres(db, no_genre_model):
    no_genre_model.side_effect = lambda tag: {"egg punk": 0.83, "united states": 0.04}[tag]
    done = datetime(2026, 10, 7)
    clean = _band(db, "Clean", genres=["punk", "egg punk"], enriched_at=done)
    places = _band(db, "Places", genres=["punk", "united states"], enriched_at=done)
    pending = _band(db, "Pending", genres=["seen live"])          # not looked up yet: left alone
    db.commit()

    assert recheck_genres(db) == 1

    assert clean.enriched_at == done and places.enriched_at is None and pending.enriched_at is None
    assert db.query(GenreTag).count() == 2


async def test_when_the_genre_model_goes_down_bands_are_left_for_the_next_run(db, services, no_genre_model):
    _band(db, "A"), _band(db, "B")
    db.commit()
    services.lastfm.return_value = ["egg punk"]                  # outside the vocabulary: the model is needed

    result = await _run(db, services)

    assert (result["looked_up"], result["failed"], result["remaining"]) == (0, 2, 2)
    assert no_genre_model.call_count == 1                        # not asked again after it failed


async def test_a_rechecked_band_with_only_tags_that_arent_genres_loses_them(db, services, no_genre_model):
    no_genre_model.side_effect = lambda tag: 0.02
    band = _band(db, "Tagged", genres=["seen live", "finnish"])  # the services still have nothing better
    db.commit()

    await _run(db, services)

    db.refresh(band)
    assert band.genres == [] and band.enriched_at is not None
