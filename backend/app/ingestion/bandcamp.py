"""A Band's photo from its Bandcamp page: the band photo artists put beside their music, at full size.

Bandcamp rate limits hard (it answers most quick requests with 429), so pages are fetched one at a time, paced and
retried as the link checks are (app/ingestion/links.py). A page Bandcamp won't serve right now raises
BandcampUnavailable, so a backfill can try the Band again next run rather than settle for no photo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from app.ingestion.links import _USER_AGENT, paced_get

# The sidebar's band photo; its image id, at any of Bandcamp's sizes ("_21" is the sidebar's, "_10" the original).
_BAND_PHOTO = re.compile(r'<img\b[^>]*\bclass="band-photo"[^>]*>')
_IMAGE_ID = re.compile(r"bcbits\.com/img/(\d+)_\d+\.")
_FULL_SIZE = "https://f4.bcbits.com/img/{id}_10.jpg"


class BandcampUnavailable(Exception):
    """Bandcamp wouldn't serve the page right now (rate limited, an error, or no connection)."""


@dataclass
class BandcampPhoto:
    url: str      # the full-size photo to download
    credit: dict  # its source (Bandcamp) and page; Bandcamp gives no author or licence


def bandcamp_credit(page_url: str) -> dict:
    return {"source": "Bandcamp", "author": None, "license": None, "license_url": None, "source_url": page_url}


def bandcamp_photo(page_url: str, client: httpx.Client | None = None) -> BandcampPhoto | None:
    """The band photo on a Bandcamp page, with its credit; None when the page has none or is gone."""
    own_client = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
    try:
        response = paced_get(client, page_url)
    except httpx.HTTPError as exc:
        raise BandcampUnavailable(f"{page_url}: {exc}") from exc
    finally:
        if own_client:
            client.close()
    if response is None or response.status_code >= 500:
        raise BandcampUnavailable(f"{page_url}: {'rate limited' if response is None else response.status_code}")
    if response.status_code != 200:
        return None
    tag = _BAND_PHOTO.search(response.text)
    image = _IMAGE_ID.search(tag.group(0)) if tag else None
    return BandcampPhoto(_FULL_SIZE.format(id=image.group(1)), bandcamp_credit(page_url)) if image else None
