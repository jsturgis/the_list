"""Tests for the page fetcher's guards: which addresses it refuses, and what counts as a challenge in the way."""
import socket

import pytest

import asyncio
import gzip
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from curl_cffi import requests as curl
from fastapi.testclient import TestClient

import scraper
from scraper import (Fetcher, Identity, Refused, Target, TooLarge, allowed_client, app, browser_user_agent, check_url,
                     decode, for_log, impersonation_target, is_challenge, opens_browser, read_capped,
                     still_challenged)


def _resolves_to(*addresses):
    def resolve(host, port, proto=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, proto, "", (address, port)) for address in addresses]
    return resolve


def test_a_public_page_is_fetched_from_the_address_checked():
    assert check_url("https://www.ticketweb.com/event/x/1", resolve=_resolves_to("23.32.1.1")) == \
        Target("www.ticketweb.com", 443, "23.32.1.1")
    assert check_url("http://example.com/", resolve=_resolves_to("23.32.1.1")).port == 80


@pytest.mark.parametrize("address", ["192.168.0.74", "10.0.0.1", "127.0.0.1", "100.101.102.103", "169.254.169.254",
                                     "0.0.0.0", "::1", "fd7a:115c:a1e0::1", "::ffff:192.168.0.1", "fe80::1%eth0",
                                     "64:ff9b::7f00:1", "64:ff9b::c0a8:4a",   # NAT64 wrapping 127.0.0.1, 192.168.0.74
                                     "2002:c0a8:4a::1",                       # 6to4 wrapping 192.168.0.74
                                     "2001:0:4136:e378:8000:63bf:3fff:fdd2"])   # Teredo
def test_an_address_behind_the_server_is_refused(address):
    with pytest.raises(Refused, match="isn't a public address"):
        check_url("http://example.com/", resolve=_resolves_to(address))


def test_a_host_with_any_private_address_is_refused():
    with pytest.raises(Refused):
        check_url("http://example.com/", resolve=_resolves_to("23.32.1.1", "192.168.0.82"))


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "http:///nohost"])
def test_what_isnt_a_web_page_is_refused(url):
    with pytest.raises(Refused, match="isn't a web page"):
        check_url(url, resolve=_resolves_to("23.32.1.1"))


def test_cloudflare_challenges_and_blocks_are_seen():
    assert is_challenge(403, {"cf-mitigated": "challenge"}, "")
    assert is_challenge(403, {"server": "cloudflare"}, "<title>Attention Required! | Cloudflare</title>")
    assert is_challenge(503, {"server": "cloudflare"}, "<title>Just a moment...</title>")


def test_ticketmasters_identity_check_is_seen():
    page = "<!doctype html><html><head><noscript><title>Let's Get Your Identity Verified</title></noscript>"
    assert is_challenge(401, {}, page)
    assert still_challenged(page)
    assert not still_challenged("<title>Sunami Tickets, 2026-12-26 San Jose, CA | Ticketmaster</title>")


def test_the_sites_own_answers_are_not_challenges():
    assert not is_challenge(200, {"server": "cloudflare"}, "<title>An event</title>")
    assert not is_challenge(404, {"server": "cloudflare"}, "<title>Not found</title>")
    assert not is_challenge(530, {"server": "cloudflare"}, "<title>Error 1016</title>")
    assert not is_challenge(403, {"server": "Apache"}, "<title>Attention Required</title>")
    assert not is_challenge(401, {}, "<title>Sign in</title>")


_TARGETS = ["chrome99", "chrome131", "chrome133a", "chrome136", "chrome142", "chrome150", "chrome151",
            "chrome151_macos", "chrome152", "chrome152_macos", "chrome99_android", "chrome131_android",
            "edge101", "safari18_0", "firefox135"]
_LINUX_156 = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
_MAC_156 = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/156.0.0.0 Safari/537.36")


def test_headless_chrome_is_made_chrome_and_nothing_else():
    headless = _LINUX_156.replace("Chrome/", "HeadlessChrome/")
    assert browser_user_agent(headless) == _LINUX_156
    assert browser_user_agent(_LINUX_156) == _LINUX_156


def test_curl_imitates_the_newest_chrome_no_newer_than_the_browser():
    assert impersonation_target(_LINUX_156, _TARGETS) == "chrome152"
    assert impersonation_target(_LINUX_156.replace("156", "151"), _TARGETS) == "chrome151"
    assert impersonation_target(_LINUX_156.replace("156", "140"), _TARGETS) == "chrome136"


def test_curl_imitates_the_macs_chrome_for_a_mac_browser():
    assert impersonation_target(_MAC_156, _TARGETS) == "chrome152_macos"
    assert impersonation_target(_MAC_156.replace("156", "150"), _TARGETS) == "chrome150"   # no Mac target for 150


def test_a_plain_target_is_preferred_to_its_alternative_and_android_is_never_used():
    both = ["chrome133a", "chrome133", "chrome131"]
    assert impersonation_target(_LINUX_156.replace("156", "133"), both) == "chrome133"
    assert impersonation_target(_LINUX_156.replace("156", "133"), _TARGETS) == "chrome133a"
    assert impersonation_target(_LINUX_156.replace("156", "135"), ["chrome133a", "chrome131_android"]) == "chrome133a"


def test_a_browser_older_than_every_target_gets_the_oldest():
    assert impersonation_target(_LINUX_156.replace("156", "90"), _TARGETS) == "chrome99"


def test_both_tiers_send_the_same_identity():
    identity = Identity(_LINUX_156, {"sec-ch-ua": '"Chromium";v="156"', "sec-ch-ua-platform": '"Linux"'}, "chrome152")
    assert identity.headers() == {"User-Agent": _LINUX_156, "sec-ch-ua": '"Chromium";v="156"',
                                  "sec-ch-ua-platform": '"Linux"'}


# ── The pen test's findings (2026-11-18) ─────────────────────────────────────

def test_a_nat64_address_wrapping_a_public_one_is_public():
    check_url("http://example.com/", resolve=_resolves_to("64:ff9b::1720:101"))   # 23.32.1.1


def test_the_pin_names_an_ipv6_address_in_brackets():
    assert Target("example.com", 443, "2606:4700::1").resolve_option() == "example.com:443:[2606:4700::1]"
    assert Target("example.com", 80, "23.32.1.1").resolve_option() == "example.com:80:23.32.1.1"


class _Site(BaseHTTPRequestHandler):
    """A site on this machine: /page answers a page, /bomb a gzip that grows to 20 MB, /hop redirects to /page."""
    BOMB = gzip.compress(b"A" * 20 * 1024 * 1024)

    def do_GET(self):
        if self.path == "/hop":
            self.send_response(302)
            self.send_header("Location", "/page")
            self.end_headers()
            return
        body = self.BOMB if self.path == "/bomb" else "<title>An event</title>café".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if self.path == "/bomb":
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def site():
    server = HTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


@pytest.fixture
def fetcher():
    fetcher = Fetcher()
    fetcher.identity = Identity("Mozilla/5.0 Chrome/156.0.0.0", {}, "chrome152")
    fetcher.session = curl.Session(impersonate="chrome152")
    return fetcher


def test_curl_connects_to_the_address_checked_not_one_looked_up_again(site, fetcher):
    """DNS rebinding: a name that answers a public address for the check and a private one for the connection.
    Here the name doesn't resolve at all: the request can only reach the site through the address checked."""
    checked = Target("rebind.invalid", site, "127.0.0.1")
    with patch("scraper.check_url", return_value=checked):
        answer = fetcher._request(f"http://rebind.invalid:{site}/page")
    assert (answer.status_code, answer.text) == (200, "<title>An event</title>café")


def test_each_redirect_is_checked_and_pinned(site, fetcher):
    checked = Target("rebind.invalid", site, "127.0.0.1")
    with patch("scraper.check_url", return_value=checked) as check:
        answer = fetcher._request(f"http://rebind.invalid:{site}/hop")
    assert [c.args[0] for c in check.call_args_list] == [f"http://rebind.invalid:{site}/hop",
                                                         f"http://rebind.invalid:{site}/page"]
    assert answer.url == f"http://rebind.invalid:{site}/page"


def test_a_decompression_bomb_is_stopped_at_the_cap(site, fetcher):
    with patch("scraper.check_url", return_value=Target("bomb.invalid", site, "127.0.0.1")), \
         patch("scraper.read_capped", side_effect=lambda chunks: read_capped(chunks, limit=1024 * 1024)):
        with pytest.raises(TooLarge, match="larger than 1 MB"):
            fetcher._request(f"http://bomb.invalid:{site}/bomb")


def test_reading_stops_once_past_the_cap():
    sent = []

    def chunks():
        for _ in range(100):
            sent.append(1)
            yield b"x" * 1000
    with pytest.raises(TooLarge):
        read_capped(chunks(), limit=2500)
    assert len(sent) == 3   # not the other 97


def test_a_page_is_decoded_in_its_charset():
    assert decode("café".encode("latin-1"), "text/html; charset=ISO-8859-1") == "café"
    assert decode("café".encode(), "text/html") == "café"
    assert decode(b"caf\xe9", "text/html; charset=nonsense") == "caf\ufffd"


def test_the_browser_opens_only_for_the_sites_listed():
    assert opens_browser("https://www.bandsintown.com/e/1")
    assert opens_browser("https://bandsintown.com./a/1")
    assert not opens_browser("https://evil-bandsintown.com/e/1")
    assert not opens_browser("https://bandsintown.com.evil.example/e/1")
    assert not opens_browser("https://www.example.com/")
    assert opens_browser("https://www.ticketmaster.com/sunami-san-jose-california-12-26-2026/event/1C006550FA24DFD7")
    assert not opens_browser("https://ticketmaster.evyy.net/c/1/2/3")


def test_a_challenge_from_a_site_not_listed_is_answered_as_it_is(fetcher):
    challenge = scraper.Answer(403, {"cf-mitigated": "challenge"}, "https://evil.example/",
                               "<title>Just a moment</title>")
    with patch.object(fetcher, "_request", return_value=challenge), patch.object(fetcher, "_browse") as browse:
        page = asyncio.run(fetcher.fetch("https://evil.example/"))
    browse.assert_not_called()
    assert (page.status, page.via) == (403, "request")


def test_a_page_waited_for_is_opened_in_the_browser_on_a_site_listed(fetcher):
    drawn = scraper.Page(200, "https://www.ticketmaster.com/e/1", "<li data-price></li>", "browser")
    with patch.object(scraper, "check_url"), patch.object(fetcher, "_request") as request, \
            patch.object(fetcher, "_browse", return_value=drawn) as browse:
        page = asyncio.run(fetcher.fetch("https://www.ticketmaster.com/e/1", wait_for="[data-price]"))
    request.assert_not_called()
    browse.assert_called_once_with("https://www.ticketmaster.com/e/1", "[data-price]")
    assert page.via == "browser"


def test_waiting_for_a_page_on_a_site_not_listed_doesnt_open_the_browser(fetcher):
    answer = scraper.Answer(200, {}, "https://evil.example/", "<title>An event</title>")
    with patch.object(fetcher, "_request", return_value=answer), patch.object(fetcher, "_browse") as browse:
        page = asyncio.run(fetcher.fetch("https://evil.example/", wait_for="[data-price]"))
    browse.assert_not_called()
    assert page.via == "request"


@pytest.mark.parametrize("address, allowed", [
    ("100.101.102.103", True), ("fd7a:115c:a1e0::5", True), ("127.0.0.1", True), ("::1", True),
    ("192.168.0.185", False), ("172.17.0.1", False), ("8.8.8.8", False), ("testclient", False), (None, False)])
def test_only_the_tailnet_and_the_machine_itself_are_answered(address, allowed):
    assert allowed_client(address) is allowed


def test_a_request_from_the_home_network_is_refused():
    with patch("scraper.TOKEN", "t0k"):
        response = TestClient(app, client=("192.168.0.185", 5000)).post(
            "/fetch", json={"url": "https://example.com/"}, headers={"Authorization": "Bearer t0k"})
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_no_api_docs_are_served(path):
    assert TestClient(app, client=("100.101.102.103", 5000)).get(path).status_code == 404


def test_errors_say_what_kind_of_wrong_not_what_was_found():
    with patch("scraper.TOKEN", "t0k"), patch("scraper.fetcher") as fake:
        client = TestClient(app, client=("100.101.102.103", 5000))
        fake.fetch.side_effect = Refused("router.lan isn't a public address")
        refused = client.post("/fetch", json={"url": "http://router.lan/"}, headers={"Authorization": "Bearer t0k"})
        fake.fetch.side_effect = ConnectionError("connect to 192.168.0.1 port 80 failed: Connection refused")
        failed = client.post("/fetch", json={"url": "http://x.example/"}, headers={"Authorization": "Bearer t0k"})
    assert refused.json() == {"detail": "not a public web page"}
    assert failed.json() == {"detail": "couldn't fetch the page"}


def test_urls_are_logged_without_their_query():
    assert for_log("https://example.com/e/1?token=secret#x") == "https://example.com/e/1"
