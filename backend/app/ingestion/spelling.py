"""A Band's name put right when it's listed misspelt: "Sunamo" for Sunami, "Middrift" for Midrift.

When neither MusicBrainz nor Discogs has an artist with a new Band's name, the name may be misspelt. Last.fm's search
gives names like it with each artist's listeners; the likeliest is looked up on MusicBrainz and Discogs as a Band would
be, and only if one of them has that artist is it the Band's name. Otherwise the name stays as listed.

The likeliest of the close names (at least _SIMILARITY alike, with as many words) is the most listened to, when it's
clearly so: at least _LEAD times the listeners of the next. The Bands Steve lists tour everywhere, so where an artist
is from says nothing; how many people listen to it does. Looks alone would mislead: "Sunao" (388 listeners) is closer
to "Sunamo" than Sunami (174,502) is. Neither MusicBrainz's search (it ranks by looks) nor Discogs' (it doesn't find
misspellings: nothing for "Middrift") gives close names to choose from.

A Band whose name was put right keeps the listed spelling (Band.spellings), so the next listing that spells it so is
the same Band without asking the services again.
"""
from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from typing import Callable

from app.slugs import slugify

logger = logging.getLogger(__name__)

# How alike a name must be to be the listed one misspelt: "Sunamo" and "Sunami" are 0.83, "Middrift" and "Midrift"
# 0.93; "Outta Pocket" and "Pocket Rocket" 0.48.
_SIMILARITY = 0.8
# How far ahead in listeners the likeliest must be: Sunami has 9 times Senamo's, Midrift 108 times Midriff's.
_LEAD = 3


@dataclass(frozen=True)
class Candidate:
    name: str
    listeners: int = 0


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


def same_name(a: str, b: str) -> bool:
    """Whether two names are one as written, but for case and spacing."""
    return " ".join(a.casefold().split()) == " ".join(b.casefold().split())


def close_names(name: str, candidates: list[Candidate]) -> list[Candidate]:
    """The candidates that could be `name` misspelt: as many words, at least _SIMILARITY alike, and not the same name.
    A name that differs only in punctuation counts as close: "Time Spent /Driving" is Time Spent Driving, which
    MusicBrainz's search (it wants the exact name) doesn't find either. Leaving it out because it has the same slug
    left Time Spent Burning (90 listeners) as the only close name."""
    words = len(name.split())
    return [c for c in candidates if len(c.name.split()) == words and not same_name(c.name, name)
            and _similarity(name, c.name) >= _SIMILARITY]


def likeliest(name: str, candidates: list[Candidate]) -> str | None:
    """The close name (see close_names) most likely to be `name` spelt right: the most listened to, when it has at
    least _LEAD times the listeners of the next (one name spelt several ways counts once); else None."""
    best: dict[str, Candidate] = {}
    for c in close_names(name, candidates):
        key = slugify(c.name)
        if key not in best or c.listeners > best[key].listeners:
            best[key] = c
    ranked = sorted(best.values(), key=lambda c: -c.listeners)
    if not ranked or ranked[0].listeners <= 0:
        return None
    if len(ranked) > 1 and ranked[0].listeners < _LEAD * ranked[1].listeners:
        return None
    return ranked[0].name


@dataclass(frozen=True)
class Respelling:
    name: str          # the Band's name, spelt right
    found: dict        # what MusicBrainz has for it (app/pipeline/enrichment.py _enrich_band)
    discogs: object    # its Discogs artist, or None


def respell(name: str, candidates: Callable[[str], list[Candidate]], lookup: Callable[[str], dict],
            discogs: Callable[[str, dict], object]) -> Respelling | None:
    """`name` spelt right, when MusicBrainz or Discogs has the likeliest close name (see likeliest) as an artist;
    else None. `lookup` is the MusicBrainz lookup (its "mbid" is None without a match), `discogs` the Discogs one."""
    fixed = likeliest(name, candidates(name))
    if not fixed:
        return None
    found = lookup(fixed)
    artist = None if found.get("mbid") else discogs(fixed, found)
    if not found.get("mbid") and artist is None:
        logger.info("spelling: %r looks like %r, which neither MusicBrainz nor Discogs has; kept as listed",
                    name, fixed)
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
