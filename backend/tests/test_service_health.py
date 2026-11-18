"""Telling a service that's down from one that has nothing (app/ingestion/service_health.py)."""
from __future__ import annotations

import httpx
import musicbrainzngs
import pytest

from app.ingestion.discogs import discogs_artist
from app.ingestion.lastfm import lastfm_tags
from app.ingestion.service_health import ServiceError, failures, is_outage, note_failure

_REQUEST = httpx.Request("GET", "https://example.com/")


def _status(code: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError("x", request=_REQUEST, response=httpx.Response(code, request=_REQUEST))


class _HTTPError(Exception):
    def __init__(self, code):
        self.code = code


@pytest.mark.parametrize("exc, outage", [
    (httpx.ConnectError("refused"), True),
    (httpx.ReadTimeout("slow"), True),
    (TimeoutError(), True),
    (_status(503), True),
    (_status(429), True),
    (_status(401), True),          # a rejected key: nothing was looked up
    (_status(404), False),         # it doesn't know it
    (ServiceError("Last.fm error 11"), True),
    (KeyError("imageinfo"), False),   # an answer without the field
    (ValueError("bad"), False),
    (musicbrainzngs.NetworkError(cause=OSError()), True),
    (musicbrainzngs.ResponseError(cause=_HTTPError(503)), True),
    (musicbrainzngs.ResponseError(cause=_HTTPError(404)), False),
])
def test_is_outage(exc, outage):
    assert is_outage(exc) is outage


def test_only_outages_are_counted():
    before = failures()
    note_failure("Discogs", _status(404))
    note_failure("Discogs", _status(502))
    assert failures() - before == {"Discogs": 1}


def _lastfm(payload: dict) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))


def test_last_fm_not_knowing_the_artist_isnt_an_outage():
    before = failures()
    assert lastfm_tags("Nobody", None, api_key="k", client=_lastfm({"error": 6, "message": "not found"})) == []
    assert not failures() - before


def test_last_fm_answering_with_an_error_is_an_outage():
    before = failures()
    assert lastfm_tags("Uniform", None, api_key="k", client=_lastfm({"error": 11, "message": "offline"})) == []
    assert failures() - before == {"Last.fm": 1}


def test_discogs_not_answering_is_an_outage():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    before = failures()
    client = httpx.Client(transport=httpx.MockTransport(refuse))
    assert discogs_artist("Uniform", [], client=client, key="k", secret="s") is None
    assert failures() - before == {"Discogs": 1}
