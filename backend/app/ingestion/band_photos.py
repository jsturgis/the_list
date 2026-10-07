"""Band photos, kept with the data: downloaded at ingest, resized, re-encoded as WebP, and saved in the images
folder on the data branch (settings.images_path), so the site serves its own copies instead of hot-linking.

A stored photo is named by Band id and a short hash of its content ("bands/728-3f9c2a1b7e.webp"), so a changed
photo gets a new name and caches never show a stale one. The Band's image_url holds that path, relative to the
images folder; site_path() turns it into the site's URL. A replaced photo's old file is deleted. A stored photo
gets its focal point (image_focus, app/ingestion/photo_focus.py), from the faces in it, so the site crops around
them; a photo that changes or goes takes its focal point with it.

A photo that's gone (404/410), isn't an image, or is too big counts as none. A temporary failure (rate limit,
server error, timeout) keeps the remote URL, so the next ingest tries again.
"""
from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.ingestion.photo_focus import detect_faces, focus_for, photo_focus_of
from app.models.band import Band

logger = logging.getLogger(__name__)

MAX_WIDTH = 800
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # some Wikimedia originals are scans or panoramas; no Band photo needs more
_GONE = (404, 410)
_QUALITY = 80
_USER_AGENT = "the-list/0.1 (https://github.com/jsturgis/the_list)"  # Wikimedia rejects requests without one
_SITE_PREFIX = "/images/"


def is_stored(image_url: str | None) -> bool:
    """Whether an image is a stored photo (a path in the images folder) rather than a remote URL."""
    return bool(image_url) and not image_url.startswith(("http://", "https://"))


def site_path(image_url: str | None) -> str | None:
    """The URL the site serves an image at: a stored photo under /images/, a remote URL as it is."""
    return _SITE_PREFIX + image_url if is_stored(image_url) else image_url


def _webp(data: bytes) -> bytes | None:
    """The image resized to at most MAX_WIDTH wide (aspect kept, never enlarged) as WebP, or None if it isn't one."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            # Cameras store photos sideways with an orientation tag; WebP drops the tag, so apply it first.
            img = ImageOps.exif_transpose(img)
            if img.width > MAX_WIDTH:
                img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)), Image.LANCZOS)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "transparency" in img.info or img.mode in ("LA", "P") else "RGB")
            out = io.BytesIO()
            img.save(out, "WEBP", quality=_QUALITY, method=6)
            return out.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        return None


def _focus(data: bytes, band: Band) -> dict | None:
    """The stored photo's focal point; None if it can't be worked out (python -m app.cli photo-focus tries again)."""
    try:
        return photo_focus_of(data)
    except Exception:
        logger.warning("band photos: couldn't find the focal point of %s's photo", band.name, exc_info=True)
        return None


def save_band_photo(band: Band, url: str, images_dir: str | Path, client: httpx.Client | None = None) -> bool:
    """Download `url`, store it as the Band's photo, and point the Band at it. True if stored.

    On failure the Band keeps a photo it already has stored; a remote URL it was saved with is dropped, since
    no photo beats a hot-linked or broken one.
    """
    own_client = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
    gone = False  # the photo itself is missing or unusable, not just unavailable right now
    data = None
    try:
        with client.stream("GET", url) as response:
            if response.status_code == 200:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_DOWNLOAD_BYTES:
                        break
                too_big = len(body) > MAX_DOWNLOAD_BYTES
                data = None if too_big else _webp(bytes(body))
                gone = data is None
            else:
                gone = response.status_code in _GONE
    except httpx.HTTPError:
        pass  # timeouts, network errors: try again next ingest
    finally:
        if own_client:
            client.close()

    if data is None:
        logger.info("band photos: couldn't use %s for %s (%s)", url, band.name, "gone" if gone else "will retry")
        if gone and not is_stored(band.image_url):
            band.image_url = None
            band.image_credit = None  # a credit goes with its photo
        return False

    relative = f"bands/{band.id}-{hashlib.sha256(data).hexdigest()[:10]}.webp"
    images_dir = Path(images_dir)
    (images_dir / relative).parent.mkdir(parents=True, exist_ok=True)
    (images_dir / relative).write_bytes(data)
    old = band.image_url
    band.image_url = relative
    band.image_focus = _focus(data, band)
    if is_stored(old) and old != relative:
        (images_dir / old).unlink(missing_ok=True)
    return True


def save_band_photos(bands: list[Band], images_dir: str | Path, fallbacks: dict[str, list[dict]] | None = None) -> int:
    """Store the photo of every Band whose image is still a remote URL. Returns how many were stored.

    `fallbacks` maps a Band's name to the photos after its chosen one, in order ({"url", "credit"}: Discogs', then
    the edition's with no credit): when the chosen photo turns out to be gone, the next is tried, with its own
    credit. A temporary failure stops there, keeping that photo for the next ingest to retry. A photo is never worth
    failing an ingest over: anything unexpected for one Band is logged and skipped.
    """
    pending = [b for b in bands if b.image_url and not is_stored(b.image_url)]
    stored = 0
    if not pending:
        return stored
    with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT}) as client:
        for band in pending:
            try:
                if save_band_photo(band, band.image_url, images_dir, client):
                    stored += 1
                    continue
                for fallback in (fallbacks or {}).get(band.name, []):
                    if band.image_url is not None:  # kept for a retry after a temporary failure
                        break
                    band.image_url, band.image_credit = fallback["url"], fallback["credit"]
                    if save_band_photo(band, fallback["url"], images_dir, client):
                        stored += 1
                        break
            except Exception:
                logger.warning("band photos: skipped %s", band.name, exc_info=True)
    return stored


def fill_photo_focus(db: Session, images_dir: str | Path, recompute: bool = False, batch_size: int = 100) -> dict[str, int]:
    """Give every Band with a stored photo and no focal point its focal point, from its file in the images folder
    (`recompute`: every Band with a stored photo). No network. The same photo always gets the same point, so running
    it again changes nothing; it commits every `batch_size` Bands, so a stopped run keeps what it did.

    Returns how many Bands it gave a focal point, how many of those photos have faces and how many faces in all, and
    how many it skipped because the photo's file is missing or unreadable (they're left without one)."""
    images_dir = Path(images_dir)
    query = db.query(Band).filter(Band.image_url.is_not(None))
    if not recompute:
        query = query.filter(Band.image_focus.is_(None))
    bands = [b for b in query.order_by(Band.id) if is_stored(b.image_url)]
    counts = {"bands": 0, "with_faces": 0, "faces": 0, "skipped": 0}
    for done, band in enumerate(bands, 1):
        try:
            with Image.open(images_dir / band.image_url) as image:
                image.load()
                faces = detect_faces(image)
                band.image_focus = focus_for(faces, image.width, image.height)
        except (OSError, UnidentifiedImageError, ValueError):
            logger.warning("photo focus: skipped %s: can't read %s", band.name, band.image_url)
            counts["skipped"] += 1
            continue
        counts["bands"] += 1
        counts["with_faces"] += bool(faces)
        counts["faces"] += len(faces)
        if done % batch_size == 0:
            db.commit()
    db.commit()
    logger.info("photo focus: %(bands)d bands (%(with_faces)d with faces, %(faces)d faces); %(skipped)d skipped", counts)
    return counts
