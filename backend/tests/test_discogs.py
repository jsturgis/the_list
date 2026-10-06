"""Tests for finding a Band on Discogs (members, image, page) and its genres and styles."""
from __future__ import annotations

import httpx
import pytest

from app.ingestion import discogs
from app.ingestion.discogs import discogs_artist, discogs_genres

_API = "https://api.discogs.com"
_LINKS = [{"type": "discogs", "url": "https://www.discogs.com/artist/252431-Dying-Fetus"}]


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(discogs._time, "sleep", lambda s: None)


def _artist(artist_id=252431, name="Dying Fetus"):
    return {
        "id": artist_id, "name": name, "uri": f"https://www.discogs.com/artist/{artist_id}-Dying-Fetus",
        "members": [{"name": "Jason Netherton", "active": False}, {"name": "John Gallagher (2)", "active": True}],
        "images": [{"type": "secondary", "uri": "https://i.discogs.com/second.jpg"},
                   {"type": "primary", "uri": "https://i.discogs.com/primary.jpg"}],
    }


def _client(routes, seen=None, fail=False):
    """Discogs stand-in: `routes` maps a path (and optional query) to JSON; 404 otherwise."""
    def handler(request):
        if seen is not None:
            seen.append(request)
        if fail:
            raise httpx.ConnectTimeout("slow", request=request)
        key = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        for route, body in routes.items():
            if key == route or request.url.path == route:
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={"message": "The requested resource was not found."})
    return httpx.Client(transport=httpx.MockTransport(handler))


_CREDS = {"key": "k", "secret": "s"}


def test_finds_the_artist_through_the_musicbrainz_link():
    seen = []
    found = discogs_artist("Dying Fetus", _LINKS, client=_client({"/artists/252431": _artist()}, seen), **_CREDS)
    assert found.id == 252431
    assert found.page_url == "https://www.discogs.com/artist/252431-Dying-Fetus"
    assert found.members == [{"name": "Jason Netherton", "active": False}, {"name": "John Gallagher", "active": True}]
    assert found.image_url == "https://i.discogs.com/primary.jpg"   # the primary image, not the first
    assert seen[0].headers["Authorization"] == "Discogs key=k, secret=s"
    assert "the-list" in seen[0].headers["User-Agent"]


def test_without_a_link_a_single_exact_name_match_counts():
    routes = {"/database/search": {"results": [{"title": "Chat Pile", "id": 7258502},
                                               {"title": "Chat Pile Tribute", "id": 1}]},
              "/artists/7258502": _artist(7258502, "Chat Pile")}
    seen = []
    assert discogs_artist("chat pile", [], client=_client(routes, seen), **_CREDS).id == 7258502
    search = seen[0].url.params
    assert (search["type"], search["q"], search["per_page"]) == ("artist", "chat pile", "100")  # the widest page


def test_the_disambiguation_suffix_is_ignored_when_matching_names():
    routes = {"/database/search": {"results": [{"title": "Uniform (3)", "id": 9}]}, "/artists/9": _artist(9, "Uniform (3)")}
    assert discogs_artist("Uniform", [], client=_client(routes), **_CREDS).id == 9


@pytest.mark.parametrize("results", [
    [{"title": "Uniform", "id": 1}, {"title": "Uniform (2)", "id": 2}],   # several exact matches: ambiguous
    [{"title": "Uniformity", "id": 3}],                                  # no exact match
    [],
])
def test_no_match_unless_exactly_one_artist_has_exactly_the_name(results):
    assert discogs_artist("Uniform", [], client=_client({"/database/search": {"results": results}}), **_CREDS) is None


def test_an_artist_without_an_image_or_members():
    bare = {**_artist(), "images": [], "members": []}
    found = discogs_artist("Dying Fetus", _LINKS, client=_client({"/artists/252431": bare}), **_CREDS)
    assert (found.image_url, found.members) == (None, [])


def test_errors_timeouts_and_missing_credentials_mean_nothing():
    assert discogs_artist("Dying Fetus", _LINKS, client=_client({}), **_CREDS) is None           # 404
    assert discogs_artist("Dying Fetus", _LINKS, client=_client({}, fail=True), **_CREDS) is None
    seen = []
    assert discogs_artist("Dying Fetus", _LINKS, client=_client({"/artists/252431": _artist()}, seen),
                          key=None, secret=None) is None
    assert seen == []


def test_genres_are_the_most_common_styles_then_genres_across_main_masters():
    routes = {
        "/artists/252431/releases": {"releases": [
            {"type": "master", "role": "Main", "id": 1}, {"type": "release", "role": "Main", "id": 9},
            {"type": "master", "role": "Appearance", "id": 8}, {"type": "master", "role": "Main", "id": 2},
            {"type": "master", "role": "Main", "id": 3}, {"type": "master", "role": "Main", "id": 4}]},
        "/masters/1": {"genres": ["Rock"], "styles": ["Death Metal", "Grindcore"]},
        "/masters/2": {"genres": ["Rock"], "styles": ["Death Metal"]},
        "/masters/3": {"genres": ["Rock", "Electronic"], "styles": ["Brutal Death Metal"]},
        "/masters/4": {"genres": ["Jazz"], "styles": ["Free Jazz"]},     # a fourth master isn't read
    }
    seen = []
    assert discogs_genres(252431, client=_client(routes, seen), **_CREDS) == [
        "death metal", "grindcore", "brutal death metal", "rock", "electronic"]
    assert not any(r.url.path in ("/masters/4", "/masters/8") for r in seen)  # only 3 of the Band's own masters


def test_genres_are_empty_on_errors_or_without_masters():
    assert discogs_genres(252431, client=_client({}), **_CREDS) == []
    assert discogs_genres(252431, client=_client({"/artists/252431/releases": {"releases": []}}), **_CREDS) == []
    assert discogs_genres(252431, client=_client({}, fail=True), **_CREDS) == []
