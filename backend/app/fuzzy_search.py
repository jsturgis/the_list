"""The band-or-venue search behind the `search` show filter.

Mirrors the frontend's `lib/fuzzySearch.ts` exactly, so the API and the static site's browser
filter match the same Shows; change both together.
"""
from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[\W_]+")


def normalize(s: str) -> str:
    """Lowercase, strip accents, and turn every run of non-alphanumerics into one space."""
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", s) if not unicodedata.category(c).startswith("M")
    )
    return _NON_ALNUM.sub(" ", stripped.lower()).strip()


def fuzzy_prefix_distance(token: str, word: str) -> int:
    """Smallest edit distance (Damerau/OSA: a swap of adjacent letters is one edit) between
    `token` and any prefix of `word`, so a partly typed word still counts."""
    m, n = len(token), len(word)
    # d[i][j]: distance between token[:i] and word[:j].
    d = [[i] + [0] * n for i in range(m + 1)]
    d[0] = list(range(n + 1))
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if token[i - 1] == word[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and token[i - 1] == word[j - 2] and token[i - 2] == word[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return min(d[m])


def _allowed_typos(token: str) -> int:
    """Typos allowed for a token: none under 5 characters, 1 up to 8, then 2. Shorter tokens with
    a typo match far too much (e.g. "rose" would match "Roberts")."""
    if len(token) < 5:
        return 0
    return 1 if len(token) < 9 else 2


def token_matches(token: str, name: str) -> bool:
    """Whether one normalized query token matches a name: a substring, or a near-miss prefix of
    one of its words."""
    n = normalize(name)
    if token in n:
        return True
    k = _allowed_typos(token)
    return k > 0 and any(fuzzy_prefix_distance(token, word) <= k for word in n.split(" "))


def matches_search(query: str, names: list[str]) -> bool:
    """Whether every word of `query` matches at least one of `names` (words may match different
    names)."""
    tokens = [t for t in normalize(query).split(" ") if t]
    return all(any(token_matches(t, name) for name in names) for t in tokens)
