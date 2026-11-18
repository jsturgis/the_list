"""The page fetcher on the home server: event pages for the Ingest jobs workflow, from a home IP (ADR 0007).

GitHub's runners are turned away by sites that block datacenter addresses (TicketWeb answers them with Cloudflare's
530) or challenge scripted clients (Bandsintown, Ticketmaster). The workflow joins the tailnet and asks this service
for the page instead: `POST /fetch {"url": ...}` with `Authorization: Bearer $SCRAPER_TOKEN` answers
`{"status", "url", "html", "via"}`, the site's own status and the page after redirects. With `"wait_for"` (a CSS
selector) a page on a site the browser opens for is opened there and read once that matches, for what its scripts
draw after it loads (Ticketmaster's prices).

A page is asked for with curl_cffi, which looks like Chrome down to its TLS handshake. When a challenge answers
that (Cloudflare's, or Ticketmaster's own: a 401 asking the browser to run its script), the page is opened in a
Patchright browser, which passes the challenge; the cookies it earns (Cloudflare's `cf_clearance`) are kept, so the
next request to that site goes through curl_cffi again until they run out.

Both present one identity, the browser's own (`Identity`): its user agent, with "HeadlessChrome" (blocked outright)
made "Chrome", and its client hints (`sec-ch-ua`...), sent by curl_cffi too, over the TLS handshake of the nearest
Chrome version curl_cffi can imitate. Cloudflare ties a cf_clearance cookie to the client it was given to, and a
user agent that disagrees with the client hints, the platform the browser's scripts report, or the other tier's is
what it looks for. The identity is read from the browser when the service starts, so a newer browser in the image
changes it with no edit here.

It only fetches public web pages, so it can't be used to reach anything behind it (the pen test of 2026-11-18):
- Every address a host resolves to must be public (not the home network, the tailnet, the machine, NAT64 or 6to4
  wrapping one), and curl_cffi then connects to the address that was checked (`RESOLVE`), so a name that answers with
  a public address and then a private one (DNS rebinding) can't slip through. Each redirect is checked the same way.
- The browser only opens for the sites listed in SCRAPER_BROWSER_SITES (Bandsintown, Ticketmaster), since any site
  can answer with a challenge's headers and title. There, its requests are checked as curl_cffi's are (by `route`,
  which can't pin the address: the browser resolves names itself); WebSockets (`route_web_socket`), service workers
  and WebRTC's direct connections are refused outright.
- A page is read up to SCRAPER_MAX_BYTES, as decompressed: a small gzip bomb can't exhaust memory.
- Requests are answered only from the tailnet and the machine itself (SCRAPER_ALLOWED_CLIENTS), though the port is
  published on every interface, and only with the token. No API docs are served, and errors say no more than what
  went wrong; the details are logged.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import secrets
import socket
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

from curl_cffi import CurlOpt
from curl_cffi import requests as curl
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TOKEN = os.environ.get("SCRAPER_TOKEN", "")
PROFILE_DIR = os.environ.get("SCRAPER_PROFILE_DIR", "/data/profile")
HEADLESS = os.environ.get("SCRAPER_HEADLESS", "true").lower() != "false"
MAX_REDIRECTS = 5
CHALLENGE_WAIT_S = 30
# How long a page asked for with wait_for is given to draw it. Not there by then (sold out: no prices), it's read as is.
READY_WAIT_S = 20
# A page larger than this, decompressed, isn't an event page: reading on would only use up memory.
MAX_BYTES = int(os.environ.get("SCRAPER_MAX_BYTES", str(15 * 1024 * 1024)))
# The sites whose challenge the browser is opened for. Anything can send a challenge's headers, and the browser runs
# a site's scripts: only sites we know need it get it.
BROWSER_SITES = tuple(site.strip().lower() for site in os.environ.get("SCRAPER_BROWSER_SITES",
                                                                      "bandsintown.com,ticketmaster.com")
                      .split(",") if site.strip())
# Who may ask: the tailnet (Tailscale's IPv4 and IPv6 ranges) and the machine itself (the container's health check).
ALLOWED_CLIENTS = tuple(ipaddress.ip_network(net.strip()) for net in os.environ.get(
    "SCRAPER_ALLOWED_CLIENTS", "100.64.0.0/10,fd7a:115c:a1e0::/48,127.0.0.0/8,::1/128").split(",") if net.strip())
# Addresses that wrap an IPv4 one, translated on the way: checked as the address they wrap.
_NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))
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
# Ticketmaster's, answered with 401 (checked 2026-11-18): its script, from /epsf/, earns cookies and reloads the page.
_TICKETMASTER_TITLE_RE = re.compile(r"<title>\s*Let's Get Your Identity Verified", re.IGNORECASE)


class Refused(ValueError):
    """Not a public web page."""


class TooLarge(ValueError):
    """The page is larger than MAX_BYTES."""


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])   # less an IPv6 zone ("fe80::1%eth0")
    if ip.version == 6:
        if any(ip in net for net in _NAT64):
            ip = ipaddress.ip_address(int(ip) & 0xFFFFFFFF)
        elif ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip.sixtofour:
            ip = ip.sixtofour
        elif ip.teredo:
            return False
    return ip.is_global   # not private, loopback, link-local, the tailnet's 100.64.0.0/10, multicast or reserved


@dataclass(frozen=True)
class Target:
    """Where a URL's request goes: its host and port, and the public address checked for it, to connect to."""
    host: str
    port: int
    address: str

    def resolve_option(self) -> str:
        """curl's RESOLVE entry pinning the host to the checked address: "host:port:address"."""
        address = f"[{self.address}]" if ":" in self.address else self.address
        return f"{self.host}:{self.port}:{address}"


def check_url(url: str, resolve=socket.getaddrinfo) -> Target:
    """Refuse what isn't a public http(s) page: every address its host resolves to must be public. Returns the
    address to connect to, so that what's connected to is what was checked."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise Refused(f"{url} isn't a web page")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = [info[4][0] for info in resolve(parts.hostname, port, proto=socket.IPPROTO_TCP)]
    except (socket.gaierror, UnicodeError, ValueError) as exc:
        raise Refused(f"{parts.hostname} doesn't resolve: {exc}") from exc
    if not addresses or not all(_is_public(address) for address in addresses):
        raise Refused(f"{parts.hostname} isn't a public address")
    return Target(parts.hostname, port, addresses[0].split("%", 1)[0])


def opens_browser(url: str) -> bool:
    """Whether the browser may open this page: its site is one of BROWSER_SITES (or a subdomain of one)."""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return any(host == site or host.endswith(f".{site}") for site in BROWSER_SITES)


def allowed_client(address: str | None) -> bool:
    """Whether a request from this address may be answered: the tailnet's, or the machine's own."""
    try:
        ip = ipaddress.ip_address((address or "").split("%", 1)[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in net for net in ALLOWED_CLIENTS)


def for_log(url: str) -> str:
    """A URL as logged: without its query, which can carry what isn't ours to keep."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def read_capped(chunks, limit: int = MAX_BYTES) -> bytes:
    """The body, read until it's done or past `limit` bytes (decompressed), which raises TooLarge."""
    body = bytearray()
    for chunk in chunks:
        body += chunk
        if len(body) > limit:
            raise TooLarge(f"the page is larger than {limit // (1024 * 1024)} MB")
    return bytes(body)


_CHARSET_RE = re.compile(r"charset=[\"']?([\w.:-]+)", re.IGNORECASE)


def decode(body: bytes, content_type: str | None) -> str:
    """The body as text, in the charset its Content-Type names (else UTF-8); what doesn't decode is replaced."""
    match = _CHARSET_RE.search(content_type or "")
    try:
        return body.decode(match.group(1) if match else "utf-8", errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def is_challenge(status: int, headers, html: str) -> bool:
    """A challenge or block page stood in front of the page, rather than the site's answer: Cloudflare's, or
    Ticketmaster's."""
    if headers.get("cf-mitigated") == "challenge":
        return True
    if status == 401 and _TICKETMASTER_TITLE_RE.search(html[:5000]):
        return True
    server = (headers.get("server") or "").lower()
    return status in (403, 429, 503) and server == "cloudflare" and bool(_CLOUDFLARE_TITLE_RE.search(html[:5000]))


def still_challenged(html: str) -> bool:
    """The browser is still on a challenge's page."""
    head = html[:5000]
    return bool(_CLOUDFLARE_TITLE_RE.search(head) or _TICKETMASTER_TITLE_RE.search(head))


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


@dataclass
class Answer:
    """curl_cffi's answer, its body read (capped)."""
    status_code: int
    headers: dict
    url: str
    text: str


class Fetcher:
    """curl_cffi first, the browser when a challenge answers it; one browser, used one page at a time."""

    def __init__(self):
        self.identity: Identity | None = None
        self.session = None
        # The session's RESOLVE pin is set for each request, so one request at a time uses it.
        self._session_lock = threading.Lock()
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
            PROFILE_DIR, channel="chromium", headless=HEADLESS, user_agent=user_agent, no_viewport=True,
            # A service worker's requests aren't the page's, so they aren't checked: none. WebRTC connects without
            # a request either: none outside a proxy, of which there is none.
            service_workers="block", args=["--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                                           "--webrtc-ip-handling-policy=disable_non_proxied_udp"])
        await self._context.route("**/*", _guard_route)
        # A WebSocket isn't a request `route` sees, so it's routed here: none, as no challenge needs one. Under
        # Patchright (1.64.4, checked 2026-11-18) the handler isn't called, but a routed WebSocket never connects: it
        # stays connecting. Recheck when Patchright changes; that the browser opens only for BROWSER_SITES is what
        # keeps a hostile page out of it in the first place.
        await self._context.route_web_socket("**/*", _refuse_web_socket)
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

    async def fetch(self, url: str, wait_for: str | None = None) -> Page:
        if wait_for and opens_browser(url):
            check_url(url)
            log.info("opening %s in the browser, for %s", for_log(url), wait_for)
            return await self._browse(url, wait_for)
        answer = await asyncio.to_thread(self._request, url)
        if not is_challenge(answer.status_code, answer.headers, answer.text):
            return Page(answer.status_code, answer.url, answer.text, "request")
        if not opens_browser(answer.url):
            log.info("a challenge (%s) answered %s, which isn't a site the browser opens for", answer.status_code,
                     for_log(answer.url))
            return Page(answer.status_code, answer.url, answer.text, "request")
        log.info("a challenge (%s) answered %s; opening it in the browser", answer.status_code, for_log(answer.url))
        return await self._browse(answer.url)

    def _request(self, url: str) -> Answer:
        for _ in range(MAX_REDIRECTS + 1):
            target = check_url(url)
            with self._session_lock:
                self.session.curl_options = {CurlOpt.RESOLVE: [target.resolve_option()]}
                response = self.session.get(url, headers={**self.identity.headers(), **_HEADERS},
                                            allow_redirects=False, timeout=30, stream=True)
                try:
                    location = response.headers.get("location")
                    if response.status_code in (301, 302, 303, 307, 308) and location:
                        url = urljoin(url, location)
                        continue
                    body = read_capped(response.iter_content())
                finally:
                    response.close()
            return Answer(response.status_code, dict(response.headers), url,
                          decode(body, response.headers.get("content-type")))
        raise Refused(f"more than {MAX_REDIRECTS} redirects")

    async def _browse(self, url: str, wait_for: str | None = None) -> Page:
        from patchright.async_api import Error as PlaywrightError

        async with self._browser_lock:
            context = self._context
            page = await context.new_page()
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                challenged, html = False, ""
                for _ in range(CHALLENGE_WAIT_S):
                    try:
                        html = await page.content()
                    except PlaywrightError:
                        # The challenge passed and is reloading the page (Ticketmaster's does): read it once loaded.
                        challenged = True
                        await page.wait_for_load_state("domcontentloaded")
                        continue
                    if not still_challenged(html):
                        break
                    challenged = True
                    await page.wait_for_timeout(1000)
                else:
                    return Page(403, page.url, html, "browser")
                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, state="attached", timeout=READY_WAIT_S * 1000)
                        html = await page.content()
                    except PlaywrightError as exc:
                        log.info("%s didn't draw %s: %s", for_log(page.url), wait_for, str(exc).splitlines()[0])
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


async def _refuse_web_socket(ws) -> None:
    log.info("refused a WebSocket to %s", for_log(ws.url))
    await ws.close()


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


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def only_the_tailnet(request: Request, call_next):
    """The port is published on every interface; only the tailnet and the machine itself are answered."""
    client = request.client.host if request.client else None
    if not allowed_client(client):
        log.warning("refused a request from %s", client)
        return JSONResponse({"detail": "not allowed from this network"}, status_code=403)
    return await call_next(request)


def authorized(authorization: str = Header("")) -> None:
    if not secrets.compare_digest(authorization.encode(), f"Bearer {TOKEN}".encode()):
        raise HTTPException(401, "not authorized")


class FetchRequest(BaseModel):
    url: str
    wait_for: str | None = Field(None, max_length=200)


@app.post("/fetch", dependencies=[Depends(authorized)])
async def fetch(request: FetchRequest) -> dict:
    # What went wrong is logged; the answer says only which kind of wrong, so it can't map what's behind the server.
    try:
        page = await fetcher.fetch(request.url, request.wait_for)
    except Refused as exc:
        log.warning("refused %s: %s", for_log(request.url), exc)
        raise HTTPException(400, "not a public web page") from exc
    except TooLarge as exc:
        log.warning("%s: %s", for_log(request.url), exc)
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:   # the site didn't answer: a timeout, a reset connection, a browser crash
        log.warning("couldn't fetch %s: %s", for_log(request.url), exc)
        raise HTTPException(502, "couldn't fetch the page") from exc
    log.info("%s %s via %s", page.status, for_log(page.url), page.via)
    return {"status": page.status, "url": page.url, "html": page.html, "via": page.via}


@app.get("/health")
def health() -> dict:
    return {"ok": True}
