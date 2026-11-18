"""An event page's HTML, for the readers in app/ingestion/ticketweb.py and app/ingestion/event_page.py.

With `settings.scraper_url` set (the Ingest jobs workflow, ADR 0007), the page is asked of the page fetcher on the
home server (scraper/), over the tailnet: GitHub's runners are turned away by TicketWeb (Cloudflare's 530) and
Bandsintown, a home IP isn't. If the fetcher can't be reached, the page is asked for directly, as without it.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

log = logging.getLogger(__name__)

# What a browser sends: some sites turn away requests without them ("Your browsing activity has been paused").
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
_SCRAPER_TIMEOUT_S = 120.0   # a challenge passed in the browser takes a while


class PageError(RuntimeError):
    """The page couldn't be fetched: the site answered with an error, or didn't answer."""


def get_page(url: str) -> tuple[str, str]:
    """The page's HTML and its URL after redirects."""
    if settings.scraper_url:
        try:
            return _from_scraper(url)
        except httpx.TransportError as exc:
            log.warning("the page fetcher at %s couldn't be reached (%s); fetching %s directly",
                        settings.scraper_url, exc, url)
    try:
        response = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PageError(str(exc)) from exc
    return response.text, str(response.url)


def _from_scraper(url: str) -> tuple[str, str]:
    response = httpx.post(f"{settings.scraper_url.rstrip('/')}/fetch", json={"url": url},
                          headers={"Authorization": f"Bearer {settings.scraper_token}"}, timeout=_SCRAPER_TIMEOUT_S)
    if response.status_code != 200:
        detail = response.json().get("detail") if response.headers.get("content-type", "").startswith(
            "application/json") else response.text[:200]
        raise PageError(f"the page fetcher answered {response.status_code}: {detail}")
    page = response.json()
    if page["status"] >= 400:
        raise PageError(f"{page['status']} from {page['url']} (through the page fetcher, by {page['via']})")
    return page["html"], page["url"]
