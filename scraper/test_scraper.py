"""Tests for the page fetcher's guards: which addresses it refuses, and what counts as Cloudflare in the way."""
import socket

import pytest

from scraper import Refused, check_url, is_cloudflare_challenge


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
