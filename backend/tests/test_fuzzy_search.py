"""Band-or-venue search tests. Keep these in step with frontend/__tests__/fuzzySearch.test.ts so
the API's `search` filter and the browser filter match the same Shows."""
from __future__ import annotations

import pytest

from app.fuzzy_search import fuzzy_prefix_distance, matches_search, normalize, token_matches


@pytest.mark.parametrize("raw, expected", [
    ("Café Du Nord", "cafe du nord"),
    ("AC/DC", "ac dc"),
    ("  The   Fox—Theater! ", "the fox theater"),
    ("Sigur Rós", "sigur ros"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize("token, word, expected", [
    ("chapel", "chapel", 0),
    ("chap", "chapel", 0),
    ("chapl", "chapel", 1),
    ("mortik", "motrik", 1),
    ("theatre", "theater", 1),
    ("fillmroe", "fillmore", 1),
    ("xyz", "chapel", 3),
])
def test_fuzzy_prefix_distance(token, word, expected):
    assert fuzzy_prefix_distance(token, word) == expected


def test_token_matches_substring_anywhere():
    assert token_matches("ox th", "The Fox Theater")


def test_tokens_under_5_characters_get_no_typo():
    assert not token_matches("rose", "Larisa Roberts")
    assert not token_matches("chpl", "The Chapel")


def test_one_typo_for_5_to_8_characters_two_from_9():
    assert token_matches("chapl", "The Chapel")
    assert token_matches("warfeild", "The Warfield")
    assert not token_matches("wrafeild", "The Warfield")
    assert token_matches("muselwite", "Charlie Musselwhite")


def test_matches_search_needs_every_word():
    names = ["The Chapel", "Rose City Band", "Motrik"]
    assert matches_search("rose chapel", names)
    assert not matches_search("rose fillmore", names)


def test_blank_query_matches_everything():
    assert matches_search("  ", ["The Chapel"])
