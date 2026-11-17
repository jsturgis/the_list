"""Venue photos, kept with the data like Band photos (app/ingestion/image_store.py, app/ingestion/band_photos.py):
downloaded, resized, re-encoded as WebP and saved in the images folder on the data branch ("venues/<id>-<hash>.webp"),
so the site serves its own copy instead of hot-linking. A Venue's photo came from the formatted editions ingested
until November 2026, as a remote URL; until it's stored the site shows none.

A photo on Wikimedia Commons is stored with its credit (author, licence, file page), which its licence requires the
site to show, looked up from the file's URL (app/ingestion/wikimedia.py). A photo from anywhere else has no credit
to show. Unlike a Band photo, a Venue photo has no focal point: it's a building, cropped from a little above centre.

A photo that's gone (404/410), isn't an image, or is too big counts as none. A temporary failure (rate limit, server
error, timeout), or a Commons photo whose credit can't be looked up right now, keeps the remote URL, so the next
ingest (or python -m app.cli venue-photos) tries again.
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.ingestion.image_store import fetch_image, is_stored, store
from app.ingestion.images import wikimedia_file_title
from app.ingestion.wikimedia import commons_credit
from app.models.venue import Venue

logger = logging.getLogger(__name__)

MAX_WIDTH = 800  # the same banner as a Band photo's (DESIGN.md)
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
_USER_AGENT = "the-list/0.1 (https://github.com/jsturgis/the_list)"  # Wikimedia rejects requests without one

__all__ = ["MAX_WIDTH", "MAX_DOWNLOAD_BYTES", "save_venue_photo", "save_venue_photos", "store_venue_photos"]


def save_venue_photo(venue: Venue, url: str, images_dir: str | Path, client: httpx.Client | None = None) -> bool:
    """Download `url`, store it as the Venue's photo with its credit, and point the Venue at it. True if stored.

    On failure the Venue keeps a photo it already has stored; a remote URL that's gone is dropped, since no photo
    beats a hot-linked or broken one.
    """
    own_client = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
    try:
        fetched = fetch_image(url, client, max_download_bytes=MAX_DOWNLOAD_BYTES, max_width=MAX_WIDTH)
        credit = None
        if fetched.data is not None and wikimedia_file_title(url):
            credit = commons_credit(url, client)
            if credit is None:  # a Commons photo isn't shown without its credit: try again next time
                logger.info("venue photos: no credit for %s's photo %s for now; will retry", venue.name, url)
                return False
    finally:
        if own_client:
            client.close()

    if fetched.data is None:
        logger.info("venue photos: couldn't use %s for %s (%s)", url, venue.name,
                    "gone" if fetched.gone else "will retry")
        if fetched.gone and not is_stored(venue.image_url):
            venue.image_url = None
            venue.image_credit = None  # a credit goes with its photo
        return False

    venue.image_url = store(fetched.data, prefix="venues", key=str(venue.id), images_dir=images_dir,
                            old=venue.image_url)
    venue.image_credit = credit
    return True


def save_venue_photos(venues: list[Venue], images_dir: str | Path) -> int:
    """Store the photo of every Venue whose image is still a remote URL. Returns how many were stored.
    A photo is never worth failing an ingest over: anything unexpected for one Venue is logged and skipped."""
    pending = [v for v in venues if v.image_url and not is_stored(v.image_url)]
    stored = 0
    if not pending:
        return stored
    with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT}) as client:
        for venue in pending:
            try:
                if save_venue_photo(venue, venue.image_url, images_dir, client):
                    stored += 1
            except Exception:
                logger.warning("venue photos: skipped %s", venue.name, exc_info=True)
    return stored


def store_venue_photos(db: Session, images_dir: str | Path) -> dict[str, int]:
    """Store every Venue's photo that's still a remote URL (python -m app.cli venue-photos), and commit.
    Returns how many were pending, how many were stored, and how many remain remote to retry."""
    venues = db.query(Venue).filter(Venue.image_url.is_not(None)).order_by(Venue.id).all()
    pending = sum(1 for v in venues if not is_stored(v.image_url))
    stored = save_venue_photos(venues, images_dir)
    db.commit()
    remote = sum(1 for v in venues if v.image_url and not is_stored(v.image_url))
    logger.info("venue photos: stored %d of %d; %d still remote", stored, pending, remote)
    return {"pending": pending, "stored": stored, "remote": remote}
