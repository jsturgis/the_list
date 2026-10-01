"""Check edition links before saving them.

The edition's links are often wrong: domains that don't exist, pages that are gone, and Bandcamp
subdomains with no artist behind them (Bandcamp sends those to its signup page with a 200). A link
counts as broken only when that's certain: the host can't be reached (DNS, connection or TLS
failure), the page is a 404 or 410, or Bandcamp redirects to signup. Anything else, including 403s
(usually a bot wall in front of a working site), 5xx errors and timeouts, keeps the link.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

import httpx

logger = logging.getLogger(__name__)

# Some sites refuse requests that don't look like a browser.
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
_WORKERS = 8


def _works(client: httpx.Client, url: str) -> bool:
    try:
        with client.stream("GET", url) as response:  # headers only; the body is never read
            final = response.url
            if response.status_code in (404, 410):
                return False
            return not (final.host == "bandcamp.com" and final.path.startswith("/signup"))
    except httpx.ConnectError:
        return False
    except Exception:
        return True  # timeouts, too many redirects, odd responses: not proof the link is broken


def check_links(urls: Iterable[str], client: httpx.Client | None = None) -> dict[str, bool]:
    """Map each URL to whether it works (False only when it's certainly broken)."""
    urls = list(dict.fromkeys(urls))
    if not urls:
        return {}
    own_client = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
    try:
        with ThreadPoolExecutor(_WORKERS) as pool:
            result = dict(zip(urls, pool.map(lambda url: _works(client, url), urls)))
    finally:
        if own_client:
            client.close()
    broken = [url for url, works in result.items() if not works]
    if broken:
        logger.info("links: skipping %d of %d links that don't work: %s", len(broken), len(result), ", ".join(broken))
    return result
