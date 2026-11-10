"""Shared download → resize → store pipeline for images kept with the data (Band photos, app/ingestion/band_photos.py;
Show flyers, app/ingestion/show_flyers.py): downloaded at ingest, resized, re-encoded as WebP, and saved in the
images folder on the data branch, hash-named so a changed image gets a new name and caches never show a stale one.
A replaced image's old file is deleted. The site serves these from the images folder rather than hot-linking.

A caller decides for itself what "gone" (404/410, or a body that isn't a usable image) should mean for its own
field — dropped, or kept as a remote URL to retry: this module only reports which it was.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

_GONE = (404, 410)
_QUALITY = 80
_SITE_PREFIX = "/images/"


def is_stored(image_url: str | None) -> bool:
    """Whether an image is a stored file (a path in the images folder) rather than a remote URL."""
    return bool(image_url) and not image_url.startswith(("http://", "https://"))


def site_path(image_url: str | None) -> str | None:
    """The URL the site serves an image at: a stored file under /images/, a remote URL as it is."""
    return _SITE_PREFIX + image_url if is_stored(image_url) else image_url


def to_webp(data: bytes, max_width: int, quality: int = _QUALITY) -> bytes | None:
    """`data` resized to at most `max_width` wide (aspect kept, never enlarged) as WebP, or None if it isn't a
    usable image."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            # Cameras store photos sideways with an orientation tag; WebP drops the tag, so apply it first.
            img = ImageOps.exif_transpose(img)
            if img.width > max_width:
                img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "transparency" in img.info or img.mode in ("LA", "P") else "RGB")
            out = io.BytesIO()
            img.save(out, "WEBP", quality=quality, method=6)
            return out.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        return None


@dataclass
class Fetched:
    """The result of downloading and converting an image. `gone`: True when the image itself is missing or
    unusable (a 404/410, or a body that isn't a decodable image, or too large) — never worth trying again with the
    same URL. False for a temporary failure (network error, rate limit, server error) — worth trying again later,
    keeping whatever URL the caller already has."""
    data: bytes | None
    gone: bool


def fetch_image(url: str, client: httpx.Client, *, max_download_bytes: int, max_width: int) -> Fetched:
    """Download `url` through `client` and convert it to WebP at `max_width`."""
    try:
        with client.stream("GET", url) as response:
            if response.status_code == 200:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > max_download_bytes:
                        break
                too_big = len(body) > max_download_bytes
                data = None if too_big else to_webp(bytes(body), max_width)
                return Fetched(data=data, gone=data is None)
            return Fetched(data=None, gone=response.status_code in _GONE)
    except httpx.HTTPError:
        return Fetched(data=None, gone=False)


def store(data: bytes, *, prefix: str, key: str, images_dir: str | Path, old: str | None) -> str:
    """Write `data` under `<prefix>/<key>-<hash of data>.webp` in the images folder, delete `old`'s file if it's a
    different stored file, and return the new path (relative to the images folder)."""
    relative = f"{prefix}/{key}-{hashlib.sha256(data).hexdigest()[:10]}.webp"
    images_dir = Path(images_dir)
    (images_dir / relative).parent.mkdir(parents=True, exist_ok=True)
    (images_dir / relative).write_bytes(data)
    if is_stored(old) and old != relative:
        (images_dir / old).unlink(missing_ok=True)
    return relative
