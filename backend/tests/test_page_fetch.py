"""Fetching an event page (app/ingestion/page_fetch.py): directly, or through the home server's page fetcher when
there is one (ADR 0007), falling back to directly when it can't be reached."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.ingestion.page_fetch import PageError, get_page

_URL = "https://www.ticketweb.com/event/x/1"
_SCRAPER = "http://truenas:8790"


def _answer(status: int, *, text: str = "", json: dict | None = None, url: str = _URL) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status, json=json, request=request) if json is not None else \
        httpx.Response(status, text=text, request=request)


@pytest.fixture
def no_scraper():
    with patch("app.ingestion.page_fetch.settings.scraper_url", ""):
        yield


@pytest.fixture
def scraper():
    with patch("app.ingestion.page_fetch.settings.scraper_url", _SCRAPER), \
         patch("app.ingestion.page_fetch.settings.scraper_token", "secret"):
        yield


@patch("app.ingestion.page_fetch.httpx.get")
def test_without_a_scraper_the_page_is_fetched_directly(get, no_scraper):
    get.return_value = _answer(200, text="<html>event</html>", url=_URL + "?x=1")
    assert get_page(_URL) == ("<html>event</html>", _URL + "?x=1")


@patch("app.ingestion.page_fetch.httpx.get")
def test_a_site_turning_the_request_away_is_a_page_error(get, no_scraper):
    get.return_value = _answer(530)
    with pytest.raises(PageError, match="530"):
        get_page(_URL)


@patch("app.ingestion.page_fetch.httpx.get")
@patch("app.ingestion.page_fetch.httpx.post")
def test_with_a_scraper_the_page_is_asked_of_it(post, get, scraper):
    post.return_value = _answer(200, json={"status": 200, "url": _URL, "html": "<html>event</html>", "via": "request"})

    assert get_page(_URL) == ("<html>event</html>", _URL)
    post.assert_called_once()
    assert post.call_args.args[0] == f"{_SCRAPER}/fetch"
    assert post.call_args.kwargs["json"] == {"url": _URL}
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer secret"}
    get.assert_not_called()


@patch("app.ingestion.page_fetch.httpx.post")
def test_the_sites_error_through_the_scraper_is_a_page_error(post, scraper):
    post.return_value = _answer(200, json={"status": 403, "url": _URL, "html": "", "via": "browser"})
    with pytest.raises(PageError, match="403 .* by browser"):
        get_page(_URL)


@patch("app.ingestion.page_fetch.httpx.post")
def test_the_scraper_refusing_is_a_page_error(post, scraper):
    post.return_value = _answer(400, json={"detail": "192.168.0.1 isn't a public address"})
    with pytest.raises(PageError, match="answered 400: 192.168.0.1 isn't a public address"):
        get_page(_URL)


@patch("app.ingestion.page_fetch.httpx.get")
@patch("app.ingestion.page_fetch.httpx.post", side_effect=httpx.ConnectError("no route to host"))
def test_a_scraper_that_cant_be_reached_falls_back_to_fetching_directly(post, get, scraper):
    get.return_value = _answer(200, text="<html>event</html>")
    assert get_page(_URL) == ("<html>event</html>", _URL)
