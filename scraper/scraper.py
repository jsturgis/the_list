"""The page fetcher on the home server: event pages for the Ingest jobs workflow, from a home IP (ADR 0007).

GitHub's runners are turned away by sites that block datacenter addresses (TicketWeb answers them with Cloudflare's
530) or challenge scripted clients (Bandsintown). The workflow joins the tailnet and asks this service for the page
instead: `POST /fetch {"url": ...}` with `Authorization: Bearer $SCRAPER_TOKEN` answers
`{"status", "url", "html", "via"}`, the site's own status and the page after redirects.

A page is asked for with curl_cffi, which looks like Chrome down to its TLS handshake. When Cloudflare challenges
that, the page is opened in a Patchright browser (headless, with a desktop Chrome user agent), which passes the
challenge; the cookies it earns (`cf_clearance`) are kept, so the next request to that site goes through curl_cffi
again with the browser's user agent until they run out.

It only fetches public web pages: an address on the home network, the tailnet or the machine itself is refused, for
the page and every redirect and browser request, so it can't be used to reach anything behind it.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import secrets
import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from curl_cffi import requests as curl
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

log = logging.getLogger("scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TOKEN = os.environ.get("SCRAPER_TOKEN", "")
# A desktop Chrome's user agent, for curl_cffi and the browser alike: Cloudflare ties a cf_clearance cookie to it.
USER_AGENT = os.environ.get("SCRAPER_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                  "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")
PROFILE_DIR = os.environ.get("SCRAPER_PROFILE_DIR", "/data/profile")
HEADLESS = os.environ.get("SCRAPER_HEADLESS", "true").lower() != "false"
MAX_REDIRECTS = 5
CHALLENGE_WAIT_S = 30
_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
# Cloudflare's own pages: "Just a moment..." (a challenge) and "Attention Required!" (a block).
_CLOUDFLARE_TITLE_RE = re.compile(r"<title>\s*(?:Just a moment|Attention Required)", re.IGNORECASE)


class Refused(ValueError):
    """Not a public web page."""


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global   # not private, loopback, link-local, the tailnet's 100.64.0.0/10, multicast or reserved


def check_url(url: str, resolve=socket.getaddrinfo) -> None:
    """Refuse what isn't a public http(s) page: every address its host resolves to must be public."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise Refused(f"{url} isn't a web page")
    try:
        addresses = {info[4][0] for info in resolve(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)}
    except (socket.gaierror, UnicodeError) as exc:
        raise Refused(f"{parts.hostname} doesn't resolve: {exc}") from exc
    if not addresses or not all(_is_public(address) for address in addresses):
        raise Refused(f"{parts.hostname} isn't a public address")


def is_cloudflare_challenge(status: int, headers, html: str) -> bool:
    """Cloudflare stood in front of the page: a challenge or block page rather than the site's answer."""
    if headers.get("cf-mitigated") == "challenge":
        return True
    server = (headers.get("server") or "").lower()
    return status in (403, 429, 503) and server == "cloudflare" and bool(_CLOUDFLARE_TITLE_RE.search(html[:5000]))


@dataclass
class Page:
    status: int
    url: str
    html: str
    via: str


class Fetcher:
    """curl_cffi first, the browser when Cloudflare challenges it; one browser, used one page at a time."""

    def __init__(self):
        self.session = curl.Session(impersonate="chrome")
        self._browser_lock = asyncio.Lock()
        self._playwright = None
        self._context = None

    async def fetch(self, url: str) -> Page:
        response = await asyncio.to_thread(self._request, url)
        if not is_cloudflare_challenge(response.status_code, response.headers, response.text):
            return Page(response.status_code, str(response.url), response.text, "request")
        log.info("Cloudflare challenged %s; opening it in the browser", url)
        return await self._browse(url)

    def _request(self, url: str):
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url)
            response = self.session.get(url, headers=_HEADERS, allow_redirects=False, timeout=30)
            location = response.headers.get("location")
            if response.status_code in (301, 302, 303, 307, 308) and location:
                url = urljoin(url, location)
                continue
            return response
        raise Refused(f"more than {MAX_REDIRECTS} redirects")

    async def _browse(self, url: str) -> Page:
        async with self._browser_lock:
            context = await self._browser()
            page = await context.new_page()
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                challenged = False
                for _ in range(CHALLENGE_WAIT_S):
                    html = await page.content()
                    if not _CLOUDFLARE_TITLE_RE.search(html[:5000]):
                        break
                    challenged = True
                    await page.wait_for_timeout(1000)
                else:
                    return Page(403, page.url, html, "browser")
                await self._keep_cookies(context)
                # A challenge passed reloads the page: the first answer's status was the challenge's.
                status = 200 if challenged or response is None else response.status
                return Page(status, page.url, html, "browser")
            finally:
                await page.close()

    async def _browser(self):
        if self._context is None:
            from patchright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                PROFILE_DIR, channel="chromium", headless=HEADLESS, user_agent=USER_AGENT, no_viewport=True)
            await self._context.route("**/*", _guard_route)
        return self._context

    async def _keep_cookies(self, context) -> None:
        """Hand the browser's cookies (cf_clearance) to curl_cffi, so the site's next page needs no browser."""
        for cookie in await context.cookies():
            self.session.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            await self._playwright.stop()


async def _guard_route(route) -> None:
    """The browser's requests (the page, its redirects, its scripts and images) go only to public addresses."""
    try:
        await asyncio.to_thread(check_url, route.request.url)
    except Refused:
        if route.request.url.startswith(("data:", "blob:")):
            await route.continue_()
        else:
            await route.abort("blockedbyclient")
        return
    await route.continue_()


fetcher: Fetcher | None = None


@asynccontextmanager
async def lifespan(_app):
    global fetcher
    if not TOKEN:
        raise RuntimeError("SCRAPER_TOKEN isn't set")
    fetcher = Fetcher()
    yield
    await fetcher.close()


app = FastAPI(lifespan=lifespan)


def authorized(authorization: str = Header("")) -> None:
    if not secrets.compare_digest(authorization.encode(), f"Bearer {TOKEN}".encode()):
        raise HTTPException(401, "not authorized")


class FetchRequest(BaseModel):
    url: str


@app.post("/fetch", dependencies=[Depends(authorized)])
async def fetch(request: FetchRequest) -> dict:
    try:
        page = await fetcher.fetch(request.url)
    except Refused as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:   # the site didn't answer: a timeout, a reset connection, a browser crash
        log.warning("couldn't fetch %s: %s", request.url, exc)
        raise HTTPException(502, f"couldn't fetch {request.url}: {exc}") from exc
    log.info("%s %s via %s", page.status, page.url, page.via)
    return {"status": page.status, "url": page.url, "html": page.html, "via": page.via}


@app.get("/health")
def health() -> dict:
    return {"ok": True}
