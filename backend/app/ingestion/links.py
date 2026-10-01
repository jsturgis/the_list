"""Check edition links before saving them.

The edition's links are often wrong: domains that don't exist, pages that are gone, and Bandcamp
subdomains with no artist behind them (Bandcamp sends those to its signup page with a 200). A link
counts as broken only when that's certain: the host can't be reached (DNS, connection or TLS
failure), the page is a 404 or 410, or Bandcamp redirects to signup. Anything else, including 403s
(usually a bot wall in front of a working site), 5xx errors and timeouts, keeps the link. Requests
are limited per host, and a 429 is retried after its Retry-After wait.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

import httpx

logger = logging.getLogger(__name__)

# Some sites refuse requests that don't look like a browser.
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
_WORKERS = 8
_PER_HOST = 2       # Bandcamp answers 429 when hit harder than this
_RETRIES = 4        # after a 429, wait as told and try again this many times
_MAX_WAIT = 30.0
_sleep = time.sleep

_host_slots: dict[str, threading.Semaphore] = {}
_host_slots_lock = threading.Lock()


def _slot(url: str) -> threading.Semaphore:
    """A slot per site: every Bandcamp artist has a subdomain, but they share one rate limit."""
    site = ".".join(httpx.URL(url).host.split(".")[-2:])
    with _host_slots_lock:
        return _host_slots.setdefault(site, threading.Semaphore(_PER_HOST))


def _retry_after(response: httpx.Response) -> float:
    try:
        return min(float(response.headers.get("Retry-After", 5)), _MAX_WAIT)
    except ValueError:
        return 5.0


def _works(client: httpx.Client, url: str) -> bool:
    for attempt in range(_RETRIES + 1):
        try:
            with _slot(url), client.stream("GET", url) as response:  # headers only
                status, final = response.status_code, response.url
                wait = _retry_after(response) if status == 429 else 0.0
        except httpx.ConnectError:
            return False
        except Exception:
            return True  # timeouts, too many redirects, odd responses: not proof the link is broken
        if status == 429:
            if attempt < _RETRIES:
                _sleep(wait)  # outside the host slot, so other hosts keep going
            continue
        if status in (404, 410):
            return False
        return not (final.host == "bandcamp.com" and final.path.startswith("/signup"))
    return True  # still rate limited: can't tell, so keep it


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
