"""Tests for checking edition image URLs before they're saved."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx

from app.ingestion.images import check_image_urls

_COMMONS = "https://upload.wikimedia.org/wikipedia/commons"
_THUMB = "https://upload.wikimedia.org/wikipedia/commons/thumb"


def _api_pages(titles: list[str]) -> dict:
    """A Wikipedia imageinfo response: Commons files are 'missing' locally but 'known' with imageinfo."""
    real = {"File:Lagwagon.png": "5/55/Lagwagon.png", "File:924 Gilman Street.JPG": "d/db/924_Gilman_Street.JPG"}
    pages = {}
    for n, title in enumerate(titles):
        page = {"ns": 6, "title": title, "missing": "", "known": "" if title in real else None}
        if title in real:
            path = real[title]
            page["imageinfo"] = [{"url": f"{_COMMONS}/{path}", "thumburl": f"{_THUMB}/{path}/960px-{path.split('/')[-1]}?utm_source=x"}]
        else:
            page.pop("known")
        pages[str(-n - 1)] = page
    return {"query": {"pages": pages}}


def _client(requests: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "en.wikipedia.org":
            titles = parse_qs(urlparse(str(request.url)).query)["titles"][0].split("|")
            return httpx.Response(200, json=_api_pages(titles))
        if request.url.host == "example.com":
            if request.url.path == "/band.jpg":
                return httpx.Response(206, headers={"Content-Type": "image/jpeg"}, content=b"\xff")
            if request.url.path == "/page":
                return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html>")
            return httpx.Response(404)
        raise httpx.ConnectError("unreachable", request=request)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_wikimedia_files_that_exist_get_their_real_thumbnail_url():
    # The edition's path for Lagwagon (0/04) is wrong; the API gives the real one (5/55), as a thumbnail.
    wrong = f"{_COMMONS}/0/04/Lagwagon.png"
    assert check_image_urls([wrong], client=_client([])) == {wrong: f"{_THUMB}/5/55/Lagwagon.png/960px-Lagwagon.png"}


def test_wikimedia_files_that_do_not_exist_are_dropped():
    made_up = f"{_COMMONS}/a/a2/Beck_in_2018.jpg"
    assert check_image_urls([made_up], client=_client([])) == {made_up: None}


def test_wikimedia_thumbnail_urls_are_checked_by_file_name():
    thumb = f"{_THUMB}/d/db/924_Gilman_Street.JPG/800px-924_Gilman_Street.JPG"
    result = check_image_urls([thumb], client=_client([]))
    assert result[thumb] == f"{_THUMB}/d/db/924_Gilman_Street.JPG/960px-924_Gilman_Street.JPG"


def test_wikimedia_files_are_looked_up_in_one_request():
    requests: list[httpx.Request] = []
    urls = [f"{_COMMONS}/0/04/Lagwagon.png", f"{_COMMONS}/a/a2/Beck_in_2018.jpg", f"{_COMMONS}/d/db/924_Gilman_Street.JPG"]
    check_image_urls(urls, client=_client(requests))
    assert len(requests) == 1


def test_other_urls_are_kept_only_when_they_load_as_an_image():
    urls = ["https://example.com/band.jpg", "https://example.com/page", "https://example.com/gone.jpg"]
    assert check_image_urls(urls, client=_client([])) == {
        "https://example.com/band.jpg": "https://example.com/band.jpg",
        "https://example.com/page": None,
        "https://example.com/gone.jpg": None,
    }


def test_unreachable_hosts_drop_the_image():
    assert check_image_urls(["https://down.example.net/x.jpg"], client=_client([])) == {"https://down.example.net/x.jpg": None}


def test_no_urls_means_no_requests():
    requests: list[httpx.Request] = []
    assert check_image_urls([], client=_client(requests)) == {}
    assert requests == []
