"""Tests for checking edition links before they're saved."""
from __future__ import annotations

import httpx

from app.ingestion.links import check_links


def _client(requests: list[str] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if requests is not None:
            requests.append(url)
        host, path = request.url.host, request.url.path
        if host == "no-such-domain.example":
            raise httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known", request=request)
        if host == "slow.example":
            raise httpx.ReadTimeout("timed out", request=request)
        if host == "nosuchband.bandcamp.com":
            return httpx.Response(302, headers={"Location": "https://bandcamp.com/signup?new_domain=nosuchband"})
        if host == "bandcamp.com" and path == "/signup":
            return httpx.Response(200)
        return httpx.Response({"/missing": 404, "/gone": 410, "/blocked": 403, "/down": 503}.get(path, 200))
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_links_that_load_are_kept():
    assert check_links(["https://venue.example/", "https://chatpile.bandcamp.com/"], client=_client()) == {
        "https://venue.example/": True, "https://chatpile.bandcamp.com/": True}


def test_missing_pages_and_domains_are_broken():
    urls = ["https://venue.example/missing", "https://venue.example/gone", "https://no-such-domain.example/"]
    assert check_links(urls, client=_client()) == {url: False for url in urls}


def test_bandcamp_pages_with_no_artist_are_broken():
    # Bandcamp sends unclaimed subdomains to its signup page, with a 200.
    assert check_links(["https://nosuchband.bandcamp.com/"], client=_client()) == {"https://nosuchband.bandcamp.com/": False}


def test_bot_blocks_server_errors_and_timeouts_are_kept():
    # A 403 is usually a bot wall in front of a working site; 5xx and timeouts may be temporary.
    urls = ["https://venue.example/blocked", "https://venue.example/down", "https://slow.example/"]
    assert check_links(urls, client=_client()) == {url: True for url in urls}


def test_each_link_is_checked_once():
    requests: list[str] = []
    check_links(["https://venue.example/", "https://venue.example/"], client=_client(requests))
    assert requests == ["https://venue.example/"]


def test_no_links_means_no_requests():
    requests: list[str] = []
    assert check_links([], client=_client(requests)) == {}
    assert requests == []


def _rate_limited_client(responses: dict[str, list[int]], requests: list[str]) -> httpx.Client:
    """Each URL answers with its listed statuses in turn (429s carry Retry-After: 3)."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requests.append(url)
        status = responses[url].pop(0) if len(responses[url]) > 1 else responses[url][0]
        return httpx.Response(status, headers={"Retry-After": "3"} if status == 429 else {})
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_rate_limited_links_are_retried_after_the_wait(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr("app.ingestion.links._sleep", waits.append)
    requests: list[str] = []
    client = _rate_limited_client({"https://a.bandcamp.com/": [429, 429, 404], "https://b.bandcamp.com/": [429, 200]}, requests)

    assert check_links(["https://a.bandcamp.com/", "https://b.bandcamp.com/"], client=client) == {
        "https://a.bandcamp.com/": False, "https://b.bandcamp.com/": True}
    assert waits.count(3.0) == 3
    assert requests.count("https://a.bandcamp.com/") == 3


def test_links_still_rate_limited_after_the_retries_are_kept(monkeypatch):
    monkeypatch.setattr("app.ingestion.links._sleep", lambda seconds: None)
    requests: list[str] = []
    client = _rate_limited_client({"https://a.bandcamp.com/": [429]}, requests)

    assert check_links(["https://a.bandcamp.com/"], client=client) == {"https://a.bandcamp.com/": True}
    assert len(requests) == 5  # the first try plus 4 retries


def test_subdomains_of_one_site_share_a_rate_limit_slot():
    from app.ingestion.links import _slot
    assert _slot("https://a.bandcamp.com/") is _slot("https://b.bandcamp.com/")
    assert _slot("https://a.bandcamp.com/") is not _slot("https://soundcloud.com/x")
