"""Pipeline jobs: weekly ingestion and daily maintenance."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import SessionLocal
from app.ingestion.gmail import fetch_latest_list_email
from app.ingestion.parser import parse_email_body
from app.ingestion.upsert import upsert_shows
from app.models.act import Act
from app.models.band import Band
from app.models.show import Show, ShowStatus
from app.models.venue import Venue
from app.pipeline.embed import batch_embed_and_index
from app.pipeline.enrichment import enrich_show


async def _run_ingestion_async(db: Optional[Session] = None) -> None:
    """Full pipeline: fetch → parse → enrich → upsert → embed."""
    _own_db = db is None
    if _own_db:
        db = SessionLocal()
    try:
        logger.info("ingestion: fetching latest email")
        text = fetch_latest_list_email()
        if not text:
            logger.info("ingestion: no email found, aborting")
            return

        raw_shows = parse_email_body(text)
        if not raw_shows:
            logger.info("ingestion: no shows parsed, aborting")
            return
        logger.info("ingestion: parsed %d shows", len(raw_shows))

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

        shows = upsert_shows(db, enriched)
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
        db.commit()
        logger.info("ingestion: done")

    except Exception:
        logger.exception("ingestion: pipeline failed")
        db.rollback()
        raise
    finally:
        if _own_db:
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
        today = date.today()
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
