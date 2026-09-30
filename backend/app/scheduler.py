"""Pipeline jobs: weekly ingestion and daily maintenance."""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session, joinedload

from app.clock import local_today
from app.config import settings
from app.database import SessionLocal
from app.ingestion.drive import fetch_latest_edition
from app.ingestion.edition import edition_meta, edition_shows
from app.ingestion.upsert import find_venue, known_region, upsert_shows
from app.models.act import Act
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.models.show import Show, ShowStatus
from app.models.venue import Venue
from app.pipeline.embed import batch_embed_and_index
from app.pipeline.enrichment import _clean_venue_name, _enrich_venue


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


def run_ingestion_pipeline() -> None:
    """Sync entry point for APScheduler."""
    asyncio.run(_run_ingestion_async())


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


scheduler = BackgroundScheduler()

scheduler.add_job(
    run_ingestion_pipeline,
    CronTrigger(day_of_week="fri", hour=18, minute=0),
    id="weekly_ingestion",
    replace_existing=True,
)

scheduler.add_job(
    run_daily_maintenance,
    CronTrigger(hour=0, minute=0),
    id="daily_maintenance",
    replace_existing=True,
)
