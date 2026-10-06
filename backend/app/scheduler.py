"""Pipeline jobs: weekly ingestion and daily maintenance, run by `python -m app.cli ingest`."""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session, joinedload

from app.clock import local_today
from app.config import settings
from app.database import SessionLocal
from app.ingestion.band_photos import save_band_photos
from app.ingestion.band_sources import photo_candidates, service_genres
from app.ingestion.discogs import discogs_artist, discogs_genres
from app.ingestion.drive import fetch_latest_edition
from app.ingestion.edition import edition_meta, edition_shows
from app.ingestion.enriched import merge_enriched
from app.ingestion.images import check_image_urls
from app.ingestion.ingest_stats import new_band_stats
from app.ingestion.joint_bands import joint_parts, split_joint_acts, split_joint_name
from app.ingestion.lastfm import lastfm_tags
from app.ingestion.links import check_links
from app.ingestion.upsert import find_venue, known_region, upsert_shows
from app.ingestion.wikimedia import commons_photo
from app.models.act import Act
from app.models.band import Band
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.models.show import Show, ShowStatus
from app.models.venue import Venue
from app.pipeline.embed import batch_embed_and_index
from app.pipeline.enrichment import _clean_venue_name, _enrich_band, _enrich_venue


_BAND_LINK_FIELDS = ("spotify_url", "soundcloud_url", "bandcamp_url", "website_url")


def _unsaved_links(db: Session, shows_data: list[dict]) -> set[str]:
    """Edition links for fields the database doesn't have yet: the only ones upsert would save."""
    links: set[str] = set()
    for data in shows_data:
        if data.get("venue_website"):
            venue = find_venue(db, data["venue_name"], None, (data["city"],)) if data["venue_name"] else None
            if not (venue and venue.website_url):
                links.add(data["venue_website"])
        for name, enrichment in data["band_enrichment"]:
            band = None
            for field in _BAND_LINK_FIELDS:
                if not enrichment.get(field):
                    continue
                band = band or db.query(Band).filter(Band.name == name).first()
                if not (band and getattr(band, field)):
                    links.add(enrichment[field])
    return links


def _apply_venue_data(data: dict, venue_data: dict) -> None:
    """Merge Google Places results into an edition show dict. Google's address wins (it's complete);
    the edition's own website and coordinates are kept when Google has none."""
    data["address"] = venue_data.get("address") or data["address"]
    data["venue_website"] = data["venue_website"] or venue_data.get("website_url")
    for key, source in [
        ("latitude", "latitude"), ("longitude", "longitude"), ("google_place_id", "google_place_id"),
        ("phone", "phone"), ("google_rating", "google_rating"), ("timezone", "timezone"),
        ("venue_description", "description"), ("venue_wikipedia_url", "wikipedia_url"), ("place_city", "city"),
    ]:
        if venue_data.get(source) is not None or key not in data:
            data[key] = venue_data.get(source)


async def _run_ingestion_async(db: Optional[Session] = None) -> None:
    """Full pipeline: fetch the newest edition from Drive → map → enrich new Venues → upsert → embed."""
    _own_db = db is None
    if _own_db:
        db = SessionLocal()

    run = IngestionRun(started_at=datetime.utcnow(), status=IngestionStatus.success)
    db.add(run)
    db.flush()

    try:
        logger.info("ingestion: fetching latest edition")
        doc, file_meta = fetch_latest_edition()
        shows_data = edition_shows(doc) if doc else []
        if not shows_data:
            logger.info("ingestion: no edition found, aborting")
            run.shows_parsed = 0
            run.status = IngestionStatus.no_email
            run.finished_at = datetime.utcnow()
            db.commit()
            return

        meta = edition_meta(doc)
        run.email_received_at = datetime.combine(meta["edition_date"], datetime.min.time())
        run.email_subject = meta["subject"]
        run.email_message_id = file_meta["file_id"]
        run.shows_parsed = len(shows_data)
        logger.info("ingestion: %d shows in %s", len(shows_data), file_meta.get("file_name"))
        if file_meta.get("enriched_events"):
            matched = merge_enriched(shows_data, file_meta["enriched_events"])
            logger.info("ingestion: filled gaps in %d shows from %s", matched, file_meta.get("enriched_file_name"))

        # Bands arrive with genres and links; only Venues we haven't seen need Google Places.
        loop = asyncio.get_event_loop()
        venue_cache: dict[tuple, dict] = {}
        for data in shows_data:
            name, city = data["venue_name"], data["city"]
            if not name or find_venue(db, name, None, (city,)):
                continue
            street = data["address"].rsplit(",", 1)[0] if data["address"] else None
            key = (name, city, street)
            if key not in venue_cache:
                logger.info("ingestion: enriching new venue %s (%s)", name, city)
                # Edition names are already clean: no LLM name clean-up or Wikipedia description.
                venue_cache[key] = await loop.run_in_executor(None, _enrich_venue, name, city or "", street, False)
            _apply_venue_data(data, venue_cache[key])

        # New names that are two Bands billed together ("Dying Fetus And Sanguisugabogg") become two Acts; real
        # Bands with "and" in the name ("Belle and Sebastian") don't. MusicBrainz decides, once per name.
        split_cache: dict[str, list[str]] = {}

        def split(name: str) -> list[str]:
            if name not in split_cache:
                known = joint_parts(name) is None or db.query(Band.id).filter(Band.name == name).first()
                split_cache[name] = [name] if known else split_joint_name(name)
            return split_cache[name]

        for data in shows_data:
            for name, halves in await loop.run_in_executor(None, split_joint_acts, data, split):
                logger.info("ingestion: %r is a joint billing: %s", name, " + ".join(halves))

        # New Bands: look them up on MusicBrainz (no LLM), once per name. The services are the source of truth;
        # the edition, whose genres are sometimes guessed from the name (Soulfly as "Soul / Funk / R&B"), is used
        # only when every service has nothing. Genres: MusicBrainz's curated genres, else Last.fm's tags, else
        # Discogs' genres and styles, else MusicBrainz's free-form tags, else the edition's.
        # Links: each one MusicBrainz has, else the edition's.
        # A Band already in the database was looked up when it was new, so it isn't tried again.
        band_cache: dict[str, dict | None] = {}
        genre_cache: dict[str, list[str]] = {}  # each new Band's genres from the services, asked once
        # For the run's stats: the new Bands that took their genres or links from the edition (app/ingestion/ingest_stats).
        edition_genres: dict[str, list[str]] = {}
        edition_links: dict[str, dict[str, str]] = {}
        for data in shows_data:
            for i, (name, enrichment) in enumerate(data["band_enrichment"]):
                if name not in band_cache:
                    if db.query(Band.id).filter(Band.name == name).first():
                        band_cache[name] = None
                    else:
                        logger.info("ingestion: looking up genres for %s", name)
                        found = await loop.run_in_executor(None, _enrich_band, name, False)
                        # Its photo on Wikimedia Commons, through MusicBrainz's Wikidata link, with its credit.
                        photo = await loop.run_in_executor(None, commons_photo, found.get("links") or [])
                        # Its Discogs artist (members, photo, page), through MusicBrainz's Discogs link or its name.
                        artist = await loop.run_in_executor(None, discogs_artist, name, found.get("links") or [])
                        band_cache[name] = {**found, "commons_photo": photo, "discogs": artist}
                found = band_cache[name]
                if found:
                    links = {k: v for k, v in found.items() if k.endswith("_url") and v}
                    links["mb_links"] = found.get("links") or []  # every MusicBrainz link, for app/band_links.py
                    # Photos, in order (app/ingestion/band_sources): Commons, Discogs, and only then the edition's.
                    # The first that loads is used; the rest are fallbacks if it turns out to be gone when downloaded.
                    artist = found.get("discogs")
                    candidates = photo_candidates(found.get("commons_photo"), artist, enrichment.get("image_url"))
                    if candidates:
                        links.update(image_url=candidates[0]["url"], image_credit=candidates[0]["credit"],
                                     image_candidates=candidates)
                    # Genres from the services in order (app/ingestion/band_sources), asked once per name; only when
                    # every service has none, the edition's.
                    if name not in genre_cache:
                        genre_cache[name] = await loop.run_in_executor(
                            None, service_genres, name, found, lastfm_tags, discogs_genres)
                    genres = genre_cache[name] or enrichment["genres"]
                    # First Show wins, as in the upsert, which only fills a Band's empty fields.
                    if genres and not genre_cache[name]:
                        edition_genres.setdefault(name, genres)
                    for field in _BAND_LINK_FIELDS:
                        if enrichment.get(field) and field not in links:
                            edition_links.setdefault(name, {}).setdefault(field, enrichment[field])
                    # Its Discogs members are saved with the Band.
                    data["band_enrichment"][i] = (name, {**enrichment, **links, "genres": genres, "discogs": artist,
                                                         "members": artist.members if artist else []})

        # The edition's image URLs are often broken: keep (or repair) only those that load.
        image_urls = [d["venue_image_url"] for d in shows_data if d.get("venue_image_url")] + [
            url for d in shows_data for _, e in d["band_enrichment"]
            for url in ([c["url"] for c in e["image_candidates"]] if e.get("image_candidates") else [e.get("image_url")])
            if url]
        if image_urls:
            checked = await loop.run_in_executor(None, check_image_urls, image_urls)
            for data in shows_data:
                if data.get("venue_image_url"):
                    data["venue_image_url"] = checked.get(data["venue_image_url"])
                for _, enrichment in data["band_enrichment"]:
                    if candidates := enrichment.get("image_candidates"):
                        # The first candidate that loads (repaired if need be); the rest stay as fallbacks.
                        loading = [{**c, "url": checked[c["url"]]} for c in candidates if checked.get(c["url"])]
                        first = loading[0] if loading else {"url": None, "credit": None}
                        enrichment.update(image_url=first["url"], image_credit=first["credit"],
                                          image_fallbacks=loading[1:])
                    elif enrichment.get("image_url"):
                        enrichment["image_url"] = checked.get(enrichment["image_url"])

        # Skip links that don't work: domains that don't exist, missing pages (Bandcamp links aren't checked).
        links = _unsaved_links(db, shows_data)
        if links:
            works = await loop.run_in_executor(None, check_links, sorted(links))
            broken = {url for url, ok in works.items() if not ok}
            for data in shows_data:
                if data.get("venue_website") in broken:
                    data["venue_website"] = None
                for _, enrichment in data["band_enrichment"]:
                    for field in _BAND_LINK_FIELDS:
                        if enrichment.get(field) in broken:
                            enrichment[field] = None

        shows_before = db.query(Show).count()
        shows = upsert_shows(db, shows_data)
        run.shows_upserted = len(shows)
        run.shows_new = db.query(Show).count() - shows_before
        db.commit()
        logger.info("ingestion: upserted %d shows (%d new)", len(shows), run.shows_new)

        # Reload with relationships for embedding
        show_ids = [s.id for s in shows]
        shows = (
            db.query(Show)
            .options(joinedload(Show.venue), joinedload(Show.acts).joinedload(Act.band))
            .filter(Show.id.in_(show_ids))
            .all()
        )

        # Photos are kept with the data: download each Band's that's still a remote URL into the images folder.
        bands = list({a.band.id: a.band for s in shows for a in s.acts}.values())
        # The photos after each new Band's chosen one, in case that one turns out to be gone (first Show wins).
        fallbacks: dict[str, list[dict]] = {}
        for d in shows_data:
            for name, e in d["band_enrichment"]:
                if e.get("image_fallbacks"):
                    fallbacks.setdefault(name, e["image_fallbacks"])
        stored = await loop.run_in_executor(None, save_band_photos, bands, settings.images_path, fallbacks)
        db.commit()
        if stored:
            logger.info("ingestion: saved %d band photos", stored)

        # How the new Bands came out: no photo, or the edition's genres, photo or links (no service had any).
        new_names = {name for name, found in band_cache.items() if found is not None}
        looked_up_at = datetime.utcnow()
        for band in bands:
            if band.name in new_names:
                band.enriched_at = looked_up_at
        for field, value in new_band_stats([b for b in bands if b.name in new_names], edition_genres,
                                           edition_links).items():
            setattr(run, field, value)
        db.commit()
        logger.info("ingestion: %s new bands; %s%% without a photo; from the edition: genres %s%%, photo %s%%, "
                    "links %s%%", run.new_bands, run.new_bands_without_photo_pct, run.new_bands_genres_from_edition_pct,
                    run.new_bands_photo_from_edition_pct, run.new_bands_links_from_edition_pct)

        logger.info("ingestion: embedding and indexing")
        await batch_embed_and_index(db, shows)

        run.finished_at = datetime.utcnow()
        db.commit()
        logger.info("ingestion: done")

    except Exception as exc:
        logger.exception("ingestion: pipeline failed")
        run.status = IngestionStatus.failure
        run.error = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-2000:]
        run.finished_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        if _own_db:
            db.close()


async def _run_venue_enrichment_async(venue_id: Optional[int] = None) -> None:
    """Re-enrich one venue (by id) or all venues, overwriting existing data."""
    db = SessionLocal()
    try:
        # Clear caches so stale data isn't returned
        _enrich_venue.cache_clear()
        _clean_venue_name.cache_clear()

        venues = (
            db.query(Venue).filter(Venue.id == venue_id).all()
            if venue_id
            else db.query(Venue).all()
        )
        logger.info("venue enrichment: refreshing %d venue(s)", len(venues))

        loop = asyncio.get_event_loop()
        for venue in venues:
            logger.info("venue enrichment: enriching %s", venue.name)
            data = await loop.run_in_executor(None, _enrich_venue, venue.name, venue.city or "")
            if not data:
                continue
            for attr, key in [
                ("website_url", "website_url"),
                ("address", "address"),
                ("google_place_id", "google_place_id"),
                ("timezone", "timezone"),
                ("phone", "phone"),
                ("description", "description"),
                ("wikipedia_url", "wikipedia_url"),
            ]:
                if data.get(key) is not None:
                    setattr(venue, attr, data[key])
            for attr in ("latitude", "longitude", "google_rating"):
                if data.get(attr) is not None:
                    setattr(venue, attr, data[attr])
            if data.get("city"):
                venue.city = data["city"]
                # Only move Regions for a known city; Google can return a neighbourhood.
                venue.region = known_region(data["city"]) or venue.region

        db.commit()
        logger.info("venue enrichment: done")
    except Exception:
        logger.exception("venue enrichment: failed")
        db.rollback()
        raise
    finally:
        db.close()


def run_daily_maintenance(db: Optional[Session] = None) -> None:
    """Mark past shows and hard-delete shows older than DATA_RETENTION_DAYS."""
    _own_db = db is None
    if _own_db:
        db = SessionLocal()
    try:
        today = local_today()
        cutoff = today - timedelta(days=settings.data_retention_days)

        db.query(Show).filter(
            Show.date < today,
            Show.status == ShowStatus.upcoming,
        ).update({Show.status: ShowStatus.past})

        for show in db.query(Show).filter(Show.date < cutoff).all():
            db.delete(show)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if _own_db:
            db.close()
