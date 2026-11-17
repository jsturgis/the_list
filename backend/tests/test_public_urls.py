"""app/ingestion/public_urls.py: URLs from pages we don't control, made safe to store, show and fetch."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.ingestion.public_urls import guarded_client, public_url, resolves_publicly, same_site


@pytest.mark.parametrize("url", [
    "https://gamh.com/calendar/", "http://www.bottomofthehill.com/iC202612.html", "https://8.8.8.8/flyer.jpg",
])
def test_public_http_urls_pass(url):
    assert public_url(url) == url


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "ftp://venue.example/flyer.jpg",
    "file:///etc/passwd", "http://localhost:11434/api/tags", "http://127.0.0.1/", "http://10.0.0.5/flyer.jpg",
    "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://printer.local/",
    "http://intranet/", "https:///nohost", "", None,
])
def test_anything_else_is_refused(url):
    assert public_url(url) is None


def test_a_relative_url_is_resolved_against_its_page():
    assert public_url("/shows/1", "https://venue.example/calendar/") == "https://venue.example/shows/1"
    assert public_url("javascript:void(0)", "https://venue.example/") is None


def test_same_site_ignores_the_subdomain():
    assert same_site("https://tickets.gamh.com/e/1", "https://gamh.com/")
    assert same_site("https://gamh.com/e/1", None, "https://www.gamh.com/calendar/")
    assert not same_site("https://scalper.example/gamh", "https://gamh.com/")


def test_a_host_resolving_to_a_private_address_is_not_public():
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.7", 0))]):
        assert not resolves_publicly("sneaky.example")
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.215.14", 0))]):
        assert resolves_publicly("venue.example")


def _client_through(handler):
    client = guarded_client(follow_redirects=True)
    client._transport = httpx.MockTransport(handler)
    return client


@patch("app.ingestion.public_urls.resolves_publicly", return_value=True)
def test_the_guarded_client_refuses_a_redirect_to_a_private_address(mock_resolves):
    def handler(request):
        if request.url.host == "venue.example":
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
        return httpx.Response(200, text="secrets")

    with _client_through(handler) as client, pytest.raises(httpx.ConnectError, match="non-public"):
        client.get("https://venue.example/flyer.jpg")


def test_the_guarded_client_refuses_a_public_looking_host_that_resolves_privately():
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0))]), \
         _client_through(lambda request: httpx.Response(200)) as client, pytest.raises(httpx.ConnectError):
        client.get("https://sneaky.example/flyer.jpg")


@patch("app.ingestion.public_urls.resolves_publicly", return_value=True)
def test_the_guarded_client_lets_public_requests_through(mock_resolves):
    with _client_through(lambda request: httpx.Response(200, text="ok")) as client:
        assert client.get("https://venue.example/flyer.jpg").text == "ok"
