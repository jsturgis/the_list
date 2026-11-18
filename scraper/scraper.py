"""The page fetcher on the home server: event pages for the Ingest jobs workflow, from a home IP (ADR 0007).

GitHub's runners are turned away by sites that block datacenter addresses (TicketWeb answers them with Cloudflare's
530) or challenge scripted clients (Bandsintown). The workflow joins the tailnet and asks this service for the page
instead: `POST /fetch {"url": ...}` with `Authorization: Bearer $SCRAPER_TOKEN` answers
`{"status", "url", "html", "via"}`, the site's own status and the page after redirects.

A page is asked for with curl_cffi, which looks like Chrome down to its TLS handshake. When Cloudflare challenges
that, the page is opened in a Patchright browser, which passes the challenge; the cookies it earns (`cf_clearance`)
are kept, so the next request to that site goes through curl_cffi again until they run out.

Both present one identity, the browser's own (`Identity`): its user agent, with "HeadlessChrome" (blocked outright)
made "Chrome", and its client hints (`sec-ch-ua`...), sent by curl_cffi too, over the TLS handshake of the nearest
Chrome version curl_cffi can imitate. Cloudflare ties a cf_clearance cookie to the client it was given to, and a
user agent that disagrees with the client hints, the platform the browser's scripts report, or the other tier's is
what it looks for. The identity is read from the browser when the service starts, so a newer browser in the image
changes it with no edit here.

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
PROFILE_DIR = os.environ.get("SCRAPER_PROFILE_DIR", "/data/profile")
HEADLESS = os.environ.get("SCRAPER_HEADLESS", "true").lower() != "false"
MAX_REDIRECTS = 5
CHALLENGE_WAIT_S = 30
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_CLIENT_HINTS = ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform")
# A page the browser is sent to so its identity can be read; it never leaves the browser. https, for a secure context.
_IDENTITY_URL = "https://identity.scraper.invalid/"
# curl_cffi's Chrome targets: "chrome142", "chrome133a", "chrome152_macos" (not the Android ones).
_TARGET_RE = re.compile(r"chrome(\d+)(a?)(_macos)?")
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


@dataclass(frozen=True)
class Identity:
    """The client both tiers present: the browser's user agent and client hints, and the curl_cffi target nearest
    its Chrome version."""
    user_agent: str
    client_hints: dict[str, str]
    impersonate: str

    def headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent, **self.client_hints}


def browser_user_agent(user_agent: str) -> str:
    """The browser's own user agent, less the "HeadlessChrome" that gives headless Chrome away."""
    return user_agent.replace("HeadlessChrome/", "Chrome/")


def impersonation_target(user_agent: str, targets) -> str:
    """The curl_cffi target nearest the user agent's Chrome: the newest no newer than it (else the oldest), on its
    platform where curl_cffi has one for the Mac."""
    major = int(re.search(r"Chrome/(\d+)", user_agent).group(1))
    mac = "Macintosh" in user_agent
    found = {}
    for target in targets:
        match = _TARGET_RE.fullmatch(target)
        if not match:
            continue
        version, alternative, macos = int(match[1]), bool(match[2]), bool(match[3])
        # Rank: same platform first, then the plain target over its "a" alternative.
        rank = (macos == mac, not alternative)
        if macos and not mac:
            continue
        if version not in found or rank > found[version][0]:
            found[version] = (rank, target)
    if not found:
        raise RuntimeError("curl_cffi has no Chrome to imitate")
    older = [version for version in found if version <= major]
    return found[max(older) if older else min(found)][1]


@dataclass
class Page:
    status: int
    url: str
    html: str
    via: str


class Fetcher:
    """curl_cffi first, the browser when Cloudflare challenges it; one browser, used one page at a time."""

    def __init__(self):
        self.identity: Identity | None = None
        self.session = None
        self._browser_lock = asyncio.Lock()
        self._playwright = None
        self._context = None

    async def start(self) -> None:
        """Start the browser and read its identity, which curl_cffi then presents too."""
        from curl_cffi.requests import BrowserType
        from patchright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        # The user agent a persistent context is given can't change, so it's read from a browser of its own first.
        probe = await self._playwright.chromium.launch(channel="chromium", headless=HEADLESS)
        try:
            user_agent = browser_user_agent(await (await probe.new_page()).evaluate("navigator.userAgent"))
        finally:
            await probe.close()
        self._context = await self._playwright.chromium.launch_persistent_context(
            PROFILE_DIR, channel="chromium", headless=HEADLESS, user_agent=user_agent, no_viewport=True)
        await self._context.route("**/*", _guard_route)
        sent = await self._sent_headers()
        self.identity = Identity(
            user_agent=sent["user-agent"],
            client_hints={name: sent[name] for name in _CLIENT_HINTS if name in sent},
            impersonate=impersonation_target(sent["user-agent"], [target.value for target in BrowserType]))
        self.session = curl.Session(impersonate=self.identity.impersonate)
        log.info("presenting %s (%s), curl_cffi as %s", self.identity.user_agent,
                 self.identity.client_hints.get("sec-ch-ua"), self.identity.impersonate)

    async def _sent_headers(self) -> dict[str, str]:
        """The headers the browser sends with a page, answered here rather than by any site."""
        sent = {}

        async def answer(route):
            sent.update(await route.request.all_headers())
            await route.fulfill(status=200, content_type="text/html", body="<title>identity</title>")

        page = await self._context.new_page()
        try:
            await page.route(f"{_IDENTITY_URL}**", answer)   # a page's routes are matched before the context's guard
            await page.goto(_IDENTITY_URL)
        finally:
            await page.close()
        return sent

    async def fetch(self, url: str) -> Page:
        response = await asyncio.to_thread(self._request, url)
        if not is_cloudflare_challenge(response.status_code, response.headers, response.text):
            return Page(response.status_code, str(response.url), response.text, "request")
        log.info("Cloudflare challenged %s; opening it in the browser", url)
        return await self._browse(url)

    def _request(self, url: str):
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url)
            response = self.session.get(url, headers={**self.identity.headers(), **_HEADERS}, allow_redirects=False,
                                        timeout=30)
            location = response.headers.get("location")
            if response.status_code in (301, 302, 303, 307, 308) and location:
                url = urljoin(url, location)
                continue
            return response
        raise Refused(f"more than {MAX_REDIRECTS} redirects")

    async def _browse(self, url: str) -> Page:
        async with self._browser_lock:
            context = self._context
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

    async def _keep_cookies(self, context) -> None:
        """Hand the browser's cookies (cf_clearance) to curl_cffi, so the site's next page needs no browser."""
        for cookie in await context.cookies():
            self.session.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._playwright is not None:
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
    await fetcher.start()
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
