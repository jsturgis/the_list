"""Tests for a Band's genre tags from Last.fm."""
from __future__ import annotations

import httpx

from app.ingestion.lastfm import lastfm_key_problem, lastfm_tags

_API = "https://ws.audioscrobbler.com/2.0/"


def _tags(*names):
    return {"artist": {"name": "Soulfly", "tags": {"tag": [{"name": n, "url": f"https://www.last.fm/tag/{n}"}
                                                          for n in names]}}}


_NOT_FOUND = {"error": 6, "message": "The artist you supplied could not be found", "links": []}


def _client(answer, seen=None):
    """Last.fm stand-in: `answer(params)` gives the JSON for each request; `seen` collects the params."""
    def handler(request):
        params = dict(request.url.params)
        if seen is not None:
            seen.append(params)
        result = answer(params)
        return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tags_by_musicbrainz_id_lower_cased_and_de_duplicated():
    seen = []
    tags = lastfm_tags("Soulfly", "832a43c7", api_key="k",
                       client=_client(lambda p: _tags("thrash metal", "Nu Metal", "nu metal", "groove metal"), seen))
    assert tags == ["thrash metal", "nu metal", "groove metal"]
    assert seen[0]["mbid"] == "832a43c7" and "artist" not in seen[0]
    assert seen[0]["method"] == "artist.getinfo" and seen[0]["api_key"] == "k"


def test_at_most_five_and_without_non_genre_tags():
    tags = lastfm_tags("Soulfly", "x", api_key="k", client=_client(lambda p: _tags(
        "seen live", "metal", "Favorites", "thrash metal", "nu metal", "groove metal", "metalcore", "hardcore")))
    assert tags == ["metal", "thrash metal", "nu metal", "groove metal", "metalcore"]


def test_by_exact_name_with_autocorrect_off_when_there_is_no_musicbrainz_id():
    seen = []
    assert lastfm_tags("Chat Pile", None, api_key="k", client=_client(lambda p: _tags("noise rock"), seen)) == ["noise rock"]
    assert seen[0]["artist"] == "Chat Pile" and seen[0]["autocorrect"] == "0" and "mbid" not in seen[0]


def test_falls_back_to_the_exact_name_when_last_fm_does_not_know_the_musicbrainz_id():
    seen = []
    tags = lastfm_tags("Chat Pile", "unknown-mbid", api_key="k",
                       client=_client(lambda p: _NOT_FOUND if "mbid" in p else _tags("sludge metal"), seen))
    assert tags == ["sludge metal"]
    assert [("mbid" in p, p.get("artist")) for p in seen] == [(True, None), (False, "Chat Pile")]


def test_a_single_tag_is_read_too():
    """Last.fm's JSON gives one tag as an object rather than a list of one."""
    single = {"artist": {"name": "X", "tags": {"tag": {"name": "Shoegaze", "url": "u"}}}}
    assert lastfm_tags("X", None, api_key="k", client=_client(lambda p: single)) == ["shoegaze"]


def test_not_found_errors_and_timeouts_give_no_tags():
    assert lastfm_tags("Gilman Youth", None, api_key="k", client=_client(lambda p: _NOT_FOUND)) == []
    assert lastfm_tags("X", None, api_key="k", client=_client(lambda p: httpx.Response(503))) == []

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)
    assert lastfm_tags("X", None, api_key="k", client=httpx.Client(transport=httpx.MockTransport(slow))) == []


def test_no_api_key_means_no_lookup():
    seen = []
    assert lastfm_tags("Soulfly", "x", api_key=None, client=_client(lambda p: _tags("metal"), seen)) == []
    assert seen == []


def test_a_namesake_found_by_name_is_rejected_when_its_musicbrainz_id_differs():
    """We know our Band's MusicBrainz id; Last.fm's same-named artist with another id is someone else."""
    def answer(p):
        if "mbid" in p:
            return _NOT_FOUND
        return {"artist": {"name": "Uniform", "mbid": "someone-elses-mbid",
                           "tags": {"tag": [{"name": "pop", "url": "u"}]}}}
    assert lastfm_tags("Uniform", "our-mbid", api_key="k", client=_client(answer)) == []


def test_a_name_match_without_a_musicbrainz_id_on_last_fm_is_kept():
    def answer(p):
        if "mbid" in p:
            return _NOT_FOUND
        return {"artist": {"name": "Uniform", "mbid": "", "tags": {"tag": [{"name": "noise rock", "url": "u"}]}}}
    assert lastfm_tags("Uniform", "our-mbid", api_key="k", client=_client(answer)) == ["noise rock"]


def test_places_vocalists_and_decades_are_not_genres():
    tags = lastfm_tags("X", None, api_key="k", client=_client(lambda p: _tags(
        "american", "punk", "USA", "female vocalists", "80s", "Bay Area", "hardcore", "UK")))
    assert tags == ["punk", "hardcore"]


def test_the_key_check_reports_a_rejected_or_missing_key():
    invalid = {"error": 10, "message": "Invalid API key - You must be granted a valid key by last.fm"}
    assert "error 10" in lastfm_key_problem("bad", client=_client(lambda p: httpx.Response(403, json=invalid)))
    assert lastfm_key_problem("good", client=_client(lambda p: _tags("pop"))) is None
    assert lastfm_key_problem("good", client=_client(lambda p: _NOT_FOUND)) is None   # a known key, unknown artist
    assert lastfm_key_problem("") == "LASTFM_API_KEY isn't set"
