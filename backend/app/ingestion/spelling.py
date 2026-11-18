"""A Band's name put right when it's listed misspelt: "Sunamo" for Sunami, "Middrift" for Midrift.

When neither MusicBrainz nor Discogs has an artist with a new Band's name, the name may be misspelt. The services
are asked for names like it (MusicBrainz's fuzzy search, Discogs' search), and the likeliest is looked up as a Band
would be. Only if a service has that artist is it the Band's name; otherwise the name stays as listed.

The likeliest of the close names (at least _SIMILARITY alike, with as many words) is the Bay Area artist among them,
as these are Bay Area listings (app/pipeline/enrichment.py _in_bay_area); else the one closest to the listed name. When
several are equally close and none is from here, none is taken: "Sunamo" is as close to Belgium's Senamo as to San
Jose's SUNAMI, and only the Bay Area says which.

A Band whose name was put right keeps the listed spelling (Band.spellings), so the next listing that spells it so is
the same Band without asking the services again.
"""
from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass
from typing import Callable

from app.slugs import slugify

logger = logging.getLogger(__name__)

# How alike a name must be to be the listed one misspelt: "Sunamo" and "Sunami" are 0.83, "Middrift" and "Midrift"
# 0.93; "Outta Pocket" and "Pocket Rocket" 0.48.
_SIMILARITY = 0.8
# Lucene's special characters, escaped in a MusicBrainz query.
_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')


@dataclass(frozen=True)
class Candidate:
    name: str
    local: bool = False   # MusicBrainz places it in the Bay Area


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


def close_names(name: str, candidates: list[Candidate]) -> list[Candidate]:
    """The candidates that could be `name` misspelt: as many words, at least _SIMILARITY alike, and not the same name
    (its slug, app/slugs.py)."""
    words = len(name.split())
    return [c for c in candidates if len(c.name.split()) == words and slugify(c.name) != slugify(name)
            and _similarity(name, c.name) >= _SIMILARITY]


def likeliest(name: str, candidates: list[Candidate]) -> str | None:
    """The close name (see close_names) most likely to be `name` spelt right: the Bay Area artist's, else the closest,
    and None when that's a tie."""
    close = close_names(name, candidates)
    local = list(dict.fromkeys(c.name for c in close if c.local))
    if len(local) == 1:
        return local[0]
    pool = local or list(dict.fromkeys(c.name for c in close))
    if not pool:
        return None
    best = max(_similarity(name, n) for n in pool)
    top = list(dict.fromkeys(n.casefold() for n in pool if _similarity(name, n) == best))
    return next(n for n in pool if _similarity(name, n) == best) if len(top) == 1 else None


def _escaped(word: str) -> str:
    """A word as a MusicBrainz (Lucene) query term: its special characters escaped ("AC\\/DC")."""
    return _LUCENE_SPECIAL.sub(r"\\\1", word)


def mb_candidates(name: str, search: Callable[..., dict], in_bay_area: Callable[[dict], bool]) -> list[Candidate]:
    """Names like `name` on MusicBrainz: its fuzzy search, each word allowing a misspelling (`artist:(sunamo~)`)."""
    terms = " ".join(f"{_escaped(word)}~" for word in name.split())
    try:
        found = search(query=f"artist:({terms})", limit=25).get("artist-list", [])
    except Exception:
        logger.info("spelling: MusicBrainz search for names like %s failed", name, exc_info=True)
        return []
    return [Candidate(a["name"], in_bay_area(a)) for a in found if a.get("name")]


@dataclass(frozen=True)
class Respelling:
    name: str          # the Band's name, spelt right
    found: dict        # what MusicBrainz has for it (app/pipeline/enrichment.py _enrich_band)
    discogs: object    # its Discogs artist, or None


def respell(name: str, candidates: Callable[[str], list[Candidate]], lookup: Callable[[str], dict],
            discogs: Callable[[str, dict], object]) -> Respelling | None:
    """`name` spelt right, when a service has the likeliest close name (see likeliest) as an artist; else None.
    `lookup` is the MusicBrainz lookup (its "mbid" is None without a match), `discogs` the Discogs one."""
    fixed = likeliest(name, candidates(name))
    if not fixed:
        return None
    found = lookup(fixed)
    artist = None if found.get("mbid") else discogs(fixed, found)
    if not found.get("mbid") and artist is None:
        logger.info("spelling: %r looks like %r, which no service has either; kept as listed", name, fixed)
        return None
    logger.info("spelling: %r is %r", name, fixed)
    return Respelling(as_listed(fixed, name), found, artist)


def as_listed(fixed: str, listed: str) -> str:
    """The right spelling in the listing's style: a name a service writes in capitals ("SUNAMI") in the listing's
    capitals when the listing doesn't write it so ("Sunamo" makes it "Sunami")."""
    if fixed.isupper() and not listed.isupper() and len(fixed.split()) == len(listed.split()):
        return " ".join(f[0] + f[1:].lower() if w[:1].isupper() else f.lower()
                        for f, w in zip(fixed.split(), listed.split()))
    return fixed
