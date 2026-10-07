"""Tests for keeping only the genres among user tags (Last.fm's, MusicBrainz's free-form ones)."""
from __future__ import annotations

import httpx
import pytest

from app.ingestion import genre_filter
from app.ingestion.genre_filter import GenreFilter, GenreModelUnavailable, ask_model, genre_model_problem, key
from app.models.genre_tag import GenreTag


def test_vocabulary_genres_are_kept_without_asking_the_model(no_genre_model):
    tags = ["Synthpop", "synth-pop", "Hip-Hop", "rnb", "Alt-Country", "drum & bass", "death metal"]
    assert GenreFilter().keep(tags) == tags      # spelled any way: "synthpop" is MusicBrainz's "synth-pop"
    no_genre_model.assert_not_called()


def test_other_tags_are_judged_by_the_model_once_and_remembered(db, no_genre_model):
    no_genre_model.side_effect = lambda tag: {"egg punk": 0.83, "united states": 0.04}[tag.lower()]
    tags = GenreFilter.load(db)
    assert tags.keep(["egg punk", "united states", "Egg Punk", "punk"]) == ["egg punk", "Egg Punk", "punk"]
    assert sorted(c.args[0] for c in no_genre_model.call_args_list) == ["egg punk", "united states"]
    tags.save(db)
    db.commit()

    no_genre_model.reset_mock()
    again = GenreFilter.load(db)                  # a later run asks nothing it's judged before
    assert again.keep(["egg punk", "United States"]) == ["egg punk"]
    no_genre_model.assert_not_called()
    row = db.get(GenreTag, "eggpunk")
    assert (row.example, row.is_genre, row.score, row.decided_by) == ("egg punk", True, 0.83, "model")


def test_a_decision_made_by_hand_wins(db, no_genre_model):
    db.add(GenreTag(tag=key("Bay Area"), example="bay area", is_genre=True, decided_by="hand",
                    decided_at=genre_filter.datetime(2026, 10, 7)))
    db.commit()
    assert GenreFilter.load(db).keep(["bay area"]) == ["bay area"]
    no_genre_model.assert_not_called()


def test_without_the_model_a_lookup_stops_and_nothing_is_recorded(db, no_genre_model):
    tags = GenreFilter.load(db)
    assert tags.keep(["punk"]) == ["punk"]                      # the vocabulary needs no model
    with pytest.raises(GenreModelUnavailable):
        tags.keep(["seen live"])
    with pytest.raises(GenreModelUnavailable):
        tags.keep(["egg punk"])
    assert no_genre_model.call_count == 1                       # not asked again after it failed
    tags.save(db)
    db.commit()
    assert db.query(GenreTag).count() == 0                      # judged next time
    no_genre_model.side_effect = lambda tag: 0.9
    assert GenreFilter.load(db).keep(["egg punk"]) == ["egg punk"]


def test_the_ingest_keeps_unknown_tags_when_the_model_is_down(no_genre_model):
    assert GenreFilter(keep_unknown=True).keep(["seen live", "punk"]) == ["seen live", "punk"]


@pytest.mark.parametrize("threshold, kept", [(0.5, ["crank wave"]), (0.7, [])])
def test_the_threshold_decides(monkeypatch, no_genre_model, threshold, kept):
    monkeypatch.setattr(genre_filter.settings, "genre_model_threshold", threshold)
    no_genre_model.return_value = 0.6
    assert GenreFilter().keep(["crank wave"]) == kept


def test_asking_the_model(monkeypatch):
    # `ask_model` here is the real one, imported before the autouse stub replaces it in genre_filter.
    seen = []

    def post(url, json, timeout):
        seen.append((url, json))
        return httpx.Response(200, json={"answers": {"genre": {"type": "noul", "noul": 0.83}}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(genre_filter.httpx, "post", post)
    assert ask_model("egg punk") == 0.83
    url, body = seen[0]
    assert url.endswith("/v1/systemone") and body["model"] == "tev1:0.8b"
    assert body["state"] == {"tag": "egg punk"} and body["questions"]["genre"]["type"] == "noul"

    calls = []

    def down(*args, **kwargs):
        calls.append(1)
        raise httpx.ConnectError("Ollama isn't running")
    monkeypatch.setattr(genre_filter.httpx, "post", down)
    monkeypatch.setattr(genre_filter.time, "sleep", lambda s: None)
    assert ask_model("egg punk") is None
    assert len(calls) == 3                                 # tried again: the runner sometimes restarts


def test_the_model_check(no_genre_model):
    assert "tev1:0.8b" in genre_model_problem()       # can't be reached
    no_genre_model.return_value = 0.97
    assert genre_model_problem() is None
