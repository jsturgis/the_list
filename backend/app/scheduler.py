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
from app.ingestion.gmail import fetch_latest_list_email
from app.ingestion.parser import parse_email_body
from app.ingestion.upsert import known_region, upsert_shows
from app.models.act import Act
from app.models.band import Band
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.models.show import Show, ShowStatus
from app.models.venue import Venue
from app.pipeline.embed import batch_embed_and_index
from app.pipeline.enrichment import _clean_venue_name, _enrich_venue, enrich_show


async def _run_ingestion_async(db: Optional[Session] = None) -> None:
    """Full pipeline: fetch → parse → enrich → upsert → embed."""
    _own_db = db is None
    if _own_db:
        db = SessionLocal()

    run = IngestionRun(started_at=datetime.utcnow(), status=IngestionStatus.success)
    db.add(run)
    db.flush()

    try:
        logger.info("ingestion: fetching latest email")
        text, email_meta = fetch_latest_list_email()
        if not text:
            logger.info("ingestion: no email found, aborting")
            run.status = IngestionStatus.no_email
            run.finished_at = datetime.utcnow()
            db.commit()
            return

        run.email_received_at = email_meta.get("email_received_at")
        run.email_subject = email_meta.get("email_subject")
        run.email_message_id = email_meta.get("email_message_id")

        raw_shows = parse_email_body(text)
        if not raw_shows:
            logger.info("ingestion: no shows parsed, aborting")
            run.shows_parsed = 0
            run.status = IngestionStatus.no_email
            run.finished_at = datetime.utcnow()
            db.commit()
            return
        logger.info("ingestion: parsed %d shows", len(raw_shows))
        run.shows_parsed = len(raw_shows)

        # Pre-load known headliners and venues to skip redundant API calls
        headliner_names = [raw.bands[0] for raw in raw_shows if raw.bands]
        venue_names = [raw.venue_name for raw in raw_shows if raw.venue_name]
        known_bands = {b.name: b for b in db.query(Band).filter(Band.name.in_(headliner_names)).all()}
        known_venues = {v.name: v for v in db.query(Venue).filter(Venue.name.in_(venue_names)).all()}

        enriched = []
        new_count = 0
        for raw in raw_shows:
            headliner = raw.bands[0] if raw.bands else None
            if headliner and headliner in known_bands:
                band = known_bands[headliner]
                venue = known_venues.get(raw.venue_name or "")
                enriched.append({
                    "date": raw.date, "bands": raw.bands, "venue_name": raw.venue_name,
                    "city": raw.city, "door_time": raw.door_time, "set_time": raw.set_time,
                    "price_raw": raw.price_raw, "age_restriction": raw.age_restriction,
                    "status": raw.status, "is_recommended": raw.is_recommended,
                    "will_sell_out": raw.will_sell_out, "is_pit": raw.is_pit,
                    "is_drink_tickets": raw.is_drink_tickets, "is_no_reentry": raw.is_no_reentry,
                    "notes": raw.notes, "raw_text": raw.raw_text,
                    "genres": band.genres or [], "spotify_url": band.spotify_url,
                    "soundcloud_url": band.soundcloud_url, "bandcamp_url": band.bandcamp_url,
                    "venue_website": venue.website_url if venue else None,
                    "address": venue.address if venue else None,
                    "latitude": venue.latitude if venue else None,
                    "longitude": venue.longitude if venue else None,
                    "google_place_id": venue.google_place_id if venue else None,
                    "phone": venue.phone if venue else None,
                    "google_rating": venue.google_rating if venue else None,
                    "timezone": venue.timezone if venue else None,
                    "venue_description": venue.description if venue else None,
                    "venue_wikipedia_url": venue.wikipedia_url if venue else None,
                })
            else:
                new_count += 1
                logger.info("ingestion: enriching [new %d] %s @ %s", new_count, headliner or "?", raw.venue_name)
                enriched.append(await enrich_show(raw))

        logger.info("ingestion: %d new, %d reused from DB", new_count, len(raw_shows) - new_count)
        run.shows_new = new_count

        shows = upsert_shows(db, enriched)
        run.shows_upserted = len(shows)
        db.commit()
        logger.info("ingestion: upserted %d shows", len(shows))

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
