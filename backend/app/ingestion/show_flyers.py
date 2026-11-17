"""Show flyers, kept with the data like Band photos (app/ingestion/image_store.py, app/ingestion/band_photos.py):
downloaded at ingest, resized, re-encoded as WebP, and saved in the images folder on the data branch, so the site
serves its own copy instead of hot-linking.

A Show's flyer_image_url is filled by app/ingestion/venue_calendar.py's matching, as a remote URL; this module
downloads and stores it, the same way save_band_photos does for Bands. Unlike a Band photo, a flyer has no focal
point (it's shown whole, never cropped to a face) and no credit (it carries no attribution requirement). A flyer
that's gone or unusable counts as none: no flyer beats a broken one. Flyer URLs come from an LLM reading a
Venue's page, so they're fetched through a client that refuses anything but public hosts (app/ingestion/public_urls.py).
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.ingestion.image_store import is_stored, fetch_image, site_path, store
from app.ingestion.public_urls import guarded_client
from app.models.show import Show, ShowStatus

logger = logging.getLogger(__name__)

MAX_WIDTH = 800
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
_USER_AGENT = "the-list/0.1 (https://github.com/jsturgis/the_list)"

__all__ = ["MAX_WIDTH", "MAX_DOWNLOAD_BYTES", "is_stored", "site_path", "save_show_flyer", "save_show_flyers",
           "prune_show_flyers"]


def save_show_flyer(show: Show, url: str, images_dir: str | Path, client: httpx.Client | None = None) -> bool:
    """Download `url`, store it as the Show's flyer, and point the Show at it. True if stored.

    On failure the Show keeps a flyer it already has stored; a remote URL it was saved with is dropped, since no
    flyer beats a hot-linked or broken one.
    """
    own_client = client is None
    client = client or guarded_client(timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
    try:
        fetched = fetch_image(url, client, max_download_bytes=MAX_DOWNLOAD_BYTES, max_width=MAX_WIDTH)
    finally:
        if own_client:
            client.close()

    if fetched.data is None:
        logger.info("show flyers: couldn't use %s for show %s (%s)", url, show.id,
                    "gone" if fetched.gone else "will retry")
        if fetched.gone:
            show.flyer_gone_url = url  # so the calendar doesn't hand the same dead URL back next time
            if not is_stored(show.flyer_image_url):
                show.flyer_image_url = None
        return False

    show.flyer_image_url = store(fetched.data, prefix="shows", key=str(show.id), images_dir=images_dir,
                                 old=show.flyer_image_url)
    return True


def save_show_flyers(shows: list[Show], images_dir: str | Path) -> int:
    """Store the flyer of every Show whose flyer_image_url is still a remote URL. Returns how many were stored.
    A flyer is never worth failing an ingest over: anything unexpected for one Show is logged and skipped."""
    pending = [s for s in shows if s.flyer_image_url and not is_stored(s.flyer_image_url)]
    stored = 0
    if not pending:
        return stored
    with guarded_client(timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT}) as client:
        for show in pending:
            try:
                if save_show_flyer(show, show.flyer_image_url, images_dir, client):
                    stored += 1
            except Exception:
                logger.warning("show flyers: skipped show %s", show.id, exc_info=True)
    return stored


def prune_show_flyers(db: Session, images_dir: str | Path, today: date) -> int:
    """Delete the flyers the site no longer shows: those of Shows before `today` or Past (the export only has
    Shows from today on, app/export.py), and any file in the flyers folder no Show points at. Returns how many
    files were deleted."""
    images_dir = Path(images_dir)
    gone = (db.query(Show).filter(Show.flyer_image_url.is_not(None))
            .filter((Show.date < today) | (Show.status == ShowStatus.past)).all())
    for show in gone:
        show.flyer_image_url = None  # its file, if it was stored, goes with the unreferenced ones below
    db.flush()  # the session doesn't autoflush: the query below must see these as cleared
    kept = {url for (url,) in db.query(Show.flyer_image_url).filter(Show.flyer_image_url.is_not(None))
            if is_stored(url)}
    deleted = 0
    folder = images_dir / "shows"
    if folder.is_dir():
        for path in folder.iterdir():
            if path.is_file() and f"shows/{path.name}" not in kept:
                path.unlink()
                deleted += 1
    return deleted
