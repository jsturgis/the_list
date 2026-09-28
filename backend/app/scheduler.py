"""Pipeline jobs: weekly ingestion and daily maintenance."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import SessionLocal
from app.ingestion.gmail import fetch_latest_list_email
from app.ingestion.parser import parse_email_body
from app.ingestion.upsert import upsert_shows
from app.models.act import Act
from app.models.show import Show, ShowStatus
from app.pipeline.embed import embed_and_index_band, embed_and_index_show
from app.pipeline.enrichment import enrich_show


async def _run_ingestion_async(db: Optional[Session] = None) -> None:
    """Full pipeline: fetch → parse → enrich → upsert → embed."""
    _own_db = db is None
    if _own_db:
        db = SessionLocal()
    try:
        text = fetch_latest_list_email()
        if not text:
            return

        raw_shows = parse_email_body(text)
        if not raw_shows:
            return

        enriched = [await enrich_show(raw) for raw in raw_shows]
        shows = upsert_shows(db, enriched)
        db.commit()

        # Reload with relationships for embedding
        show_ids = [s.id for s in shows]
        shows = (
            db.query(Show)
            .options(joinedload(Show.venue), joinedload(Show.acts).joinedload(Act.band))
            .filter(Show.id.in_(show_ids))
            .all()
        )
        for show in shows:
            await embed_and_index_show(db, show)
            if show.acts:
                await embed_and_index_band(db, show.acts[0].band)
        db.commit()

    except Exception:
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
