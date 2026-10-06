"""Bring existing Bands up to what new ones get at ingest: MusicBrainz's links, genres (MusicBrainz, Last.fm,
Discogs), Discogs' members, and a Commons or Discogs photo, all with what the Band already has (mostly edition
data) as the last fallback, by the same rules (app/ingestion/band_sources.py).

Each Band looked up gets enriched_at, so the backfill is resumable: a run takes the Bands never looked up, those
on Upcoming Shows first (they're the ones on the site), and stops at a time budget or a limit; the next run
carries on. A Band whose genres change is re-embedded for Similar Bands. One Band's failure is logged and left for
the next run; it never stops the others.

Run it with `python -m app.cli backfill` (the Backfill workflow does, on the data branch).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.clock import local_today
from app.ingestion.band_photos import _USER_AGENT, is_stored, save_band_photo
from app.ingestion.band_sources import photo_candidates, service_genres
from app.ingestion.discogs import discogs_artist, discogs_genres
from app.ingestion.lastfm import lastfm_tags
from app.ingestion.wikimedia import commons_photo
from app.models.act import Act
from app.models.band import Band
from app.models.show import Show, ShowStatus
from app.pipeline.embed import embed_and_index_band
from app.pipeline.enrichment import _enrich_band

logger = logging.getLogger(__name__)

_LINK_FIELDS = ("spotify_url", "soundcloud_url", "bandcamp_url", "website_url")


def pending_bands(db: Session) -> list[Band]:
    """Bands never looked up on the services: those on Upcoming Shows first, then the rest, oldest first."""
    upcoming = exists().where(Act.band_id == Band.id, Act.show_id == Show.id,
                              Show.status == ShowStatus.upcoming, Show.date >= local_today())
    return db.query(Band).filter(Band.enriched_at.is_(None)).order_by(upcoming.desc(), Band.id).all()


def _photo(band: Band, candidates: list[dict], images_dir: Path, client: httpx.Client) -> bool:
    """Store the first service photo that can be downloaded, by the ingest's rules: one that's gone is skipped for
    the next, and if none is left the Band keeps what it had (a photo it had at a remote URL is stored, as at
    ingest). False when a service photo couldn't be downloaded right now: the Band is left to try again next run.

    A stored photo it replaces isn't deleted here; the caller deletes it once the Band is committed."""
    had = band.image_url, band.image_credit
    for candidate in candidates:
        # Pointed at the candidate, the Band loses it only if it's gone (as at ingest), so a temporary failure shows.
        band.image_url, band.image_credit = candidate["url"], candidate["credit"]
        if save_band_photo(band, candidate["url"], images_dir, client):
            return True
        retry = band.image_url is not None
        band.image_url, band.image_credit = had
        if retry:
            return False
    if band.image_url and not is_stored(band.image_url):
        save_band_photo(band, band.image_url, images_dir, client)
    return True


def backfill_band(band: Band, images_dir: Path, client: httpx.Client) -> bool:
    """Look one Band up on the services and update it; True if its genres changed (it needs re-embedding).

    It gets enriched_at unless its service photo couldn't be downloaded right now (it's tried again next run)."""
    found = _enrich_band(band.name, False)
    mb_links = found.get("links") or []
    found = {**found, "commons_photo": commons_photo(mb_links), "discogs": discogs_artist(band.name, mb_links)}
    artist = found["discogs"]

    genres = service_genres(band.name, found, lastfm_tags, discogs_genres) or band.genres
    changed = genres != band.genres
    band.genres = genres
    if mb_links:
        band.links = mb_links
    for field in _LINK_FIELDS:
        if found.get(field):
            setattr(band, field, found[field])
    if artist and artist.members:
        band.members = artist.members
    if _photo(band, photo_candidates(found["commons_photo"], artist, None), images_dir, client):
        band.enriched_at = datetime.utcnow()
    return changed


def _delete(images_dir: Path, photo: str | None, keep: str | None) -> None:
    if is_stored(photo) and photo != keep:
        (images_dir / photo).unlink(missing_ok=True)


async def run_backfill(db: Session, images_dir: str | Path, max_minutes: float = 300, limit: int | None = None) -> dict:
    """Backfill pending Bands until done, out of time or at `limit`. Commits after each Band."""
    deadline = time.monotonic() + max_minutes * 60
    images_dir = Path(images_dir)
    loop = asyncio.get_event_loop()
    looked_up = failed = 0
    pending = pending_bands(db)
    with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT}) as client:
        for band in pending:
            if time.monotonic() >= deadline or (limit is not None and looked_up + failed >= limit):
                break
            old_photo = band.image_url
            try:
                changed = await loop.run_in_executor(None, backfill_band, band, images_dir, client)
                new_photo = band.image_url
                if changed:
                    await embed_and_index_band(db, band)
                db.commit()
                looked_up += 1
                _delete(images_dir, old_photo, keep=new_photo)    # the photo it replaced, now nothing points at it
            except Exception:
                new_photo = band.image_url
                db.rollback()
                _delete(images_dir, new_photo, keep=old_photo)    # a photo stored for the failed lookup
                failed += 1
                logger.warning("backfill: skipped %s; it'll be tried again next run", band.name, exc_info=True)
    remaining = db.query(Band).filter(Band.enriched_at.is_(None)).count()
    logger.info("backfill: looked up %d bands (%d failed); %d still to do", looked_up, failed, remaining)
    return {"looked_up": looked_up, "failed": failed, "remaining": remaining}
