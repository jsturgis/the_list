"""Tests for checking edition links before they're saved."""
from __future__ import annotations

import httpx
import pytest

from app.ingestion.links import check_links


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    """Requests to one site are normally a second apart; tests don't wait unless they ask to."""
    monkeypatch.setattr("app.ingestion.links._MIN_INTERVAL", 0.0)
    monkeypatch.setattr("app.ingestion.links._last_request", {})


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
        return httpx.Response({"/missing": 404, "/gone": 410, "/blocked": 403, "/down": 503}.get(path, 200))
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_links_that_load_are_kept():
    assert check_links(["https://venue.example/", "https://band.example/"], client=_client()) == {
        "https://venue.example/": True, "https://band.example/": True}


def test_missing_pages_and_domains_are_broken():
    urls = ["https://venue.example/missing", "https://venue.example/gone", "https://no-such-domain.example/"]
    assert check_links(urls, client=_client()) == {url: False for url in urls}


def test_bandcamp_links_are_kept_without_a_request():
    requests: list[str] = []
    urls = ["https://nosuchband.bandcamp.com/", "https://venue.example/missing"]
    assert check_links(urls, client=_client(requests)) == {
        "https://nosuchband.bandcamp.com/": True, "https://venue.example/missing": False}
    assert requests == ["https://venue.example/missing"]


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
    client = _rate_limited_client({"https://a.ratelimit.example/": [429, 429, 404], "https://b.ratelimit.example/": [429, 200]}, requests)

    assert check_links(["https://a.ratelimit.example/", "https://b.ratelimit.example/"], client=client) == {
        "https://a.ratelimit.example/": False, "https://b.ratelimit.example/": True}
    assert waits.count(3.0) == 3
    assert requests.count("https://a.ratelimit.example/") == 3


def test_links_still_rate_limited_after_the_retries_are_kept(monkeypatch):
    monkeypatch.setattr("app.ingestion.links._sleep", lambda seconds: None)
    requests: list[str] = []
    client = _rate_limited_client({"https://a.ratelimit.example/": [429]}, requests)

    assert check_links(["https://a.ratelimit.example/"], client=client) == {"https://a.ratelimit.example/": True}
    assert len(requests) == 5  # the first try plus 4 retries


def test_subdomains_of_one_site_share_a_rate_limit_slot():
    from app.ingestion.links import _slot
    assert _slot("https://a.ratelimit.example/") is _slot("https://b.ratelimit.example/")
    assert _slot("https://a.ratelimit.example/") is not _slot("https://soundcloud.com/x")


def test_requests_to_one_site_are_spaced_out(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr("app.ingestion.links._sleep", waits.append)
    monkeypatch.setattr("app.ingestion.links._MIN_INTERVAL", 60.0)
    monkeypatch.setattr("app.ingestion.links._last_request", {})

    check_links(["https://a.pacing.example/", "https://b.pacing.example/", "https://other.example/"], client=_client())

    # The second pacing.example request waits out the interval; other.example doesn't wait.
    assert len(waits) == 1 and 59 < waits[0] <= 60
