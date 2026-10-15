"""Tests for telling a Band from its namesakes on the services, and for Band corrections."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.ingestion import band_corrections
from app.ingestion.band_corrections import BandCorrection, band_correction, correct_edition
from app.ingestion.band_sources import service_genres
from app.pipeline.enrichment import _enrich_band, _mb_search


def _artist(mbid, name="Sunblind", area=None, begin_area=None, tags=0, disambiguation=None):
    """A MusicBrainz search result as musicbrainzngs gives it."""
    artist = {"id": mbid, "name": name, "tag-list": [{"name": f"tag{i}", "count": "1"} for i in range(tags)]}
    if area:
        artist["area"] = {"name": area}
    if begin_area:
        artist["begin-area"] = {"name": begin_area}
    if disambiguation:
        artist["disambiguation"] = disambiguation
    return artist


def _search(*artists):
    return patch("app.pipeline.enrichment.musicbrainzngs.search_artists", return_value={"artist-list": list(artists)})


@pytest.fixture(autouse=True)
def no_mb_lookups():
    with patch("app.pipeline.enrichment._mb_lookup", return_value={}), \
         patch("app.pipeline.enrichment._mb_genres", return_value=[]):
        yield


@pytest.fixture
def corrections(monkeypatch):
    """No corrections but the ones a test adds."""
    table: dict[str, BandCorrection] = {}
    monkeypatch.setattr(band_corrections, "CORRECTIONS", table)
    return table


# ── MusicBrainz: one artist with the name, or telling namesakes apart ─────────────────────────────────────────

def test_the_one_artist_with_exactly_the_name_matches():
    with _search(_artist("chat-pile", "Chat Pile"), _artist("other", "Chat Pile Tribute")) as search:
        assert _mb_search("chat pile")["id"] == "chat-pile"
    assert search.call_args.kwargs["limit"] == 25   # wide enough to see the namesakes, not just the top few


def test_a_namesake_from_the_bay_area_is_the_band_wherever_it_comes_in_the_results():
    dallas = _artist("dallas", "Petty Theft", begin_area="Dallas", disambiguation="Dallas tribute to Tom Petty")
    sf = _artist("sf", "Petty Theft", area="United States", begin_area="San Francisco", tags=9)
    with _search(dallas, sf):
        assert _mb_search("Petty Theft")["id"] == "sf"
    with _search(_artist("a", area="Germany", tags=3), _artist("b", area="Oakland")):
        assert _mb_search("Sunblind")["id"] == "b"


@pytest.mark.parametrize("best", [
    _artist("best", "Carnifex", disambiguation="US deathcore band"),
    _artist("best", "Carnifex", area="United States"),
    _artist("best", "Carnifex", tags=2),
])
def test_otherwise_musicbrainzs_best_match_is_the_band_when_musicbrainz_knows_something_about_it(best):
    with _search(best, _artist("other", "Carnifex", area="Germany", tags=5)):
        assert _mb_search("Carnifex")["id"] == "best"


def test_the_best_of_several_namesakes_from_the_bay_area_is_the_band():
    with _search(_artist("a", area="Germany"), _artist("b", area="Oakland"), _artist("c", begin_area="Berkeley")):
        assert _mb_search("Sunblind")["id"] == "b"


@pytest.mark.parametrize("artists", [
    # Sunblind as MusicBrainz has it: a bare German trance act and an Indonesian artist, neither the Oakland band.
    [_artist("c75c82be"), _artist("d17256ce", area="Indonesia", disambiguation="Indonesian artist")],
    [_artist("a"), _artist("b")],
])
def test_namesakes_that_cant_be_told_apart_match_none_and_say_so(artists):
    namesakes: set[str] = set()
    with _search(*artists):
        assert _mb_search("Sunblind", namesakes) is None
    assert namesakes == {"Sunblind"}


def test_a_band_with_namesakes_is_looked_up_without_them():
    with _search(_artist("c75c82be"), _artist("d17256ce", area="Indonesia")):
        found = _enrich_band("Sunblind", use_llm=False)
    assert (found["mbid"], found["links"], found["genres"]) == (None, [], [])
    assert found["namesakes"] is True


def test_a_band_on_musicbrainz_or_not_has_no_namesakes():
    with _search(_artist("chat-pile", "Chat Pile")):
        assert _enrich_band("Chat Pile", use_llm=False)["namesakes"] is False
    with _search():
        assert _enrich_band("Nobody", use_llm=False)["namesakes"] is False


# ── Last.fm: its page for a name is every artist with it ──────────────────────────────────────────────────────

def test_last_fm_isnt_asked_by_name_for_a_band_with_namesakes():
    asked = []
    lastfm = lambda name, mbid: asked.append(name) or ["trance"]
    found = {"genres": [], "mb_genres": False, "mbid": None, "namesakes": True}
    assert service_genres("Sunblind", found, lastfm, lambda artist_id: []) == []
    assert asked == []
    assert service_genres("Chat Pile", {**found, "namesakes": False}, lastfm, lambda artist_id: []) == ["trance"]


# ── Corrections: what the services and the edition get wrong, put right by hand ──────────────────────────────

def test_a_correction_is_found_by_the_bands_slug(corrections):
    corrections["sunblind"] = BandCorrection(by_name=False)
    assert band_correction("SUNBLIND") is corrections["sunblind"]
    assert band_correction("Sunblind Lion") is None


def test_a_band_corrected_as_not_findable_by_name_isnt_searched_for(corrections):
    corrections["sunblind"] = BandCorrection(by_name=False)
    with _search(_artist("c75c82be")) as search:
        found = _enrich_band("Sunblind", use_llm=False)
    search.assert_not_called()
    assert (found["mbid"], found["namesakes"]) == (None, True)


def test_a_band_corrected_with_its_musicbrainz_artist_is_looked_up_by_it(corrections):
    corrections["petty-theft"] = BandCorrection(mbid="sf")
    with _search(_artist("dallas", "Petty Theft")) as search, \
         patch("app.pipeline.enrichment._mb_lookup", return_value={
             "url-relation-list": [{"type": "bandcamp", "target": "https://pettytheft.bandcamp.com/"}]}) as lookup:
        found = _enrich_band("Petty Theft", use_llm=False)
    search.assert_not_called()
    lookup.assert_called_once_with("sf")
    assert (found["mbid"], found["bandcamp_url"], found["namesakes"]) == ("sf", "https://pettytheft.bandcamp.com/", False)


def test_a_correction_replaces_the_editions_genres_and_links(corrections):
    corrections["sunblind"] = BandCorrection(by_name=False, genres=("hardcore punk",),
                                             links={"bandcamp_url": "https://sunblindhc.bandcamp.com/"})
    edition = {"genres": ["indie rock", "alternative"], "bandcamp_url": "https://sunblind.bandcamp.com/",
               "is_local": None}
    assert correct_edition("Sunblind", edition) == {
        "genres": ["hardcore punk"], "bandcamp_url": "https://sunblindhc.bandcamp.com/", "is_local": None}
    assert correct_edition("Chat Pile", edition) is edition


def test_sunblind_is_the_oakland_hardcore_band():
    sunblind = band_correction("Sunblind")
    assert sunblind.by_name is False and sunblind.mbid is None
    assert sunblind.links == {"bandcamp_url": "https://sunblindhc.bandcamp.com/"}
