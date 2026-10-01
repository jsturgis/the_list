"""Check edition image URLs before saving them.

The edition's image URLs are often wrong: Wikimedia files that don't exist, or real files under the
wrong hashed path. Wikimedia files are looked up by name through the Wikipedia API (which also
resolves Commons files), and a file that exists gets its real thumbnail URL. Any other URL is kept
only if it loads as an image. When in doubt the image is dropped: no image beats a broken one.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from urllib.parse import unquote, urlparse

import httpx

logger = logging.getLogger(__name__)

_API = "https://en.wikipedia.org/w/api.php"
_USER_AGENT = "the-list/0.1 (https://github.com/jsturgis/the_list)"  # Wikimedia rejects requests without one
_THUMB_WIDTH = 960
_BATCH = 50  # the API's limit on titles per request


def _wikimedia_title(url: str) -> str | None:
    """'File:Name.jpg' for an upload.wikimedia.org URL (original or thumbnail), else None."""
    parsed = urlparse(url)
    if not parsed.netloc.endswith("wikimedia.org"):
        return None
    parts = parsed.path.split("/")
    name = parts[-2] if "thumb" in parts else parts[-1]
    return f"File:{unquote(name).replace('_', ' ')}" if name else None


def _resolve_wikimedia(client: httpx.Client, titles: list[str]) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for start in range(0, len(titles), _BATCH):
        batch = titles[start:start + _BATCH]
        params = {"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url",
                  "iiurlwidth": _THUMB_WIDTH, "titles": "|".join(batch)}
        try:
            data = client.get(_API, params=params).raise_for_status().json()["query"]
        except Exception:
            logger.warning("images: Wikipedia API lookup failed; dropping %d images", len(batch), exc_info=True)
            continue
        normalized = {n["to"]: n["from"] for n in data.get("normalized", [])}
        for page in data.get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            found[normalized.get(page["title"], page["title"])] = url.split("?")[0] if url else None
    return found


def _loads_as_image(client: httpx.Client, url: str) -> bool:
    try:
        response = client.get(url, headers={"Range": "bytes=0-0"}, follow_redirects=True)
    except Exception:
        return False
    return response.status_code in (200, 206) and response.headers.get("Content-Type", "").startswith("image/")


def check_image_urls(urls: Iterable[str], client: httpx.Client | None = None) -> dict[str, str | None]:
    """Map each URL to a URL that loads as an image (possibly repaired), or None to drop it."""
    urls = list(dict.fromkeys(urls))
    if not urls:
        return {}
    own_client = client is None
    client = client or httpx.Client(timeout=20, headers={"User-Agent": _USER_AGENT})
    try:
        titles = {url: _wikimedia_title(url) for url in urls}
        resolved = _resolve_wikimedia(client, sorted({t for t in titles.values() if t}))
        result = {url: resolved.get(title) if title else (url if _loads_as_image(client, url) else None)
                  for url, title in titles.items()}
    finally:
        if own_client:
            client.close()
    dropped = [url for url, checked in result.items() if checked is None]
    if dropped:
        logger.info("images: dropping %d of %d image URLs that don't load", len(dropped), len(result))
    return result
