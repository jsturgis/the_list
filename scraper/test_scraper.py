"""Tests for the page fetcher's guards: which addresses it refuses, and what counts as Cloudflare in the way."""
import socket

import pytest

from scraper import (Identity, Refused, browser_user_agent, check_url, impersonation_target,
                     is_cloudflare_challenge)


def _resolves_to(*addresses):
    def resolve(host, port, proto=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, proto, "", (address, port)) for address in addresses]
    return resolve


def test_a_public_page_is_fetched():
    check_url("https://www.ticketweb.com/event/x/1", resolve=_resolves_to("23.32.1.1"))


@pytest.mark.parametrize("address", ["192.168.0.74", "10.0.0.1", "127.0.0.1", "100.101.102.103", "169.254.169.254",
                                     "::1", "fd7a:115c:a1e0::1", "::ffff:192.168.0.1"])
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
    assert is_cloudflare_challenge(403, {"cf-mitigated": "challenge"}, "")
    assert is_cloudflare_challenge(403, {"server": "cloudflare"}, "<title>Attention Required! | Cloudflare</title>")
    assert is_cloudflare_challenge(503, {"server": "cloudflare"}, "<title>Just a moment...</title>")


def test_the_sites_own_answers_are_not_challenges():
    assert not is_cloudflare_challenge(200, {"server": "cloudflare"}, "<title>An event</title>")
    assert not is_cloudflare_challenge(404, {"server": "cloudflare"}, "<title>Not found</title>")
    assert not is_cloudflare_challenge(530, {"server": "cloudflare"}, "<title>Error 1016</title>")
    assert not is_cloudflare_challenge(403, {"server": "Apache"}, "<title>Attention Required</title>")


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
    assert impersonation_target(_LINUX_156.replace("156", "133"), ["chrome133a", "chrome133", "chrome131"]) == "chrome133"
    assert impersonation_target(_LINUX_156.replace("156", "133"), _TARGETS) == "chrome133a"
    assert impersonation_target(_LINUX_156.replace("156", "135"), ["chrome133a", "chrome131_android"]) == "chrome133a"


def test_a_browser_older_than_every_target_gets_the_oldest():
    assert impersonation_target(_LINUX_156.replace("156", "90"), _TARGETS) == "chrome99"


def test_both_tiers_send_the_same_identity():
    identity = Identity(_LINUX_156, {"sec-ch-ua": '"Chromium";v="156"', "sec-ch-ua-platform": '"Linux"'}, "chrome152")
    assert identity.headers() == {"User-Agent": _LINUX_156, "sec-ch-ua": '"Chromium";v="156"',
                                  "sec-ch-ua-platform": '"Linux"'}
