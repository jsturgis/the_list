"""Page slugs: the names in the site's Band, Venue and Show page URLs (/bands/deafheaven/).

Derived from the current names each time they're needed, never stored: the export writes them for the site and the
Alert emails link with them. Each is unique among every Band (Venue, Show) in the database, not only those
exported, so a slug doesn't move to another Band as Shows come and go, and an Alert links the slug the export has.
Shows that share a slug share a date, so they're deleted together. A renamed Band gets a new slug; its numeric URL
(/bands/12/) redirects to whatever the slug is now, so that's the permanent link.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy.orm import Session, selectinload

from app.models.band import Band
from app.models.show import Show
from app.models.venue import Venue


@dataclass(frozen=True)
class Slugs:
    bands: dict[int, str] = field(default_factory=dict)
    venues: dict[int, str] = field(default_factory=dict)
    shows: dict[int, str] = field(default_factory=dict)


def slugify(name: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    plain = re.sub(r"['’]", "", plain.replace("&", " and "))
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def _unique(wanted: dict[int, str]) -> dict[int, str]:
    """Each id its wanted slug, but where ids want the same one the lowest keeps it and the others add `-{id}`."""
    slugs: dict[int, str] = {}
    taken: set[str] = set()
    for id_ in sorted(wanted):  # every lowest id claims its slug before any suffix is made
        if wanted[id_] not in taken:
            slugs[id_] = wanted[id_]
            taken.add(wanted[id_])
    for id_ in sorted(wanted.keys() - slugs.keys()):
        slug = f"{wanted[id_]}-{id_}"
        while slug in taken:
            slug += f"-{id_}"
        slugs[id_] = slug
        taken.add(slug)
    return slugs


def _wanted(kind: str, id_: int, name: str) -> str:
    """A name's slug; `{kind}-{id}` when nothing's left of it, and `{kind}-` before one that's all digits, which
    would read as an id (/bands/311/ is Band 311's numeric URL)."""
    slug = slugify(name)
    if not slug:
        return f"{kind}-{id_}"
    return f"{kind}-{slug}" if slug.isdigit() else slug


def _show_slugs(shows: Iterable, bands: dict[int, str], venues: dict[int, str]) -> dict[int, str]:
    """`{headliner}-{date}` (`show-{date}` without Acts); with the Venue before the date where Shows share that."""
    def headliner(show) -> str:
        acts = sorted(show.acts, key=lambda a: a.position)
        return bands[acts[0].band_id] if acts else "show"

    shows = list(shows)
    plain = {s.id: f"{headliner(s)}-{s.date.isoformat()}" for s in shows}
    shared = {slug for slug, n in Counter(plain.values()).items() if n > 1}
    return _unique({
        s.id: f"{headliner(s)}-{venues[s.venue_id]}-{s.date.isoformat()}" if plain[s.id] in shared else plain[s.id]
        for s in shows
    })


def assign(bands: Iterable = (), venues: Iterable = (), shows: Iterable = ()) -> Slugs:
    """The slugs of these Bands and Venues (anything with an `id` and a `name`), each unique among its kind, and of
    these Shows (with an `id`, a `date`, a `venue_id` and `acts` with a `band_id` and `position`), whose Bands and
    Venue are among those given."""
    band_slugs = _unique({b.id: _wanted("band", b.id, b.name) for b in bands})
    venue_slugs = _unique({v.id: _wanted("venue", v.id, v.name) for v in venues})
    return Slugs(bands=band_slugs, venues=venue_slugs, shows=_show_slugs(shows, band_slugs, venue_slugs))


def site_slugs(db: Session) -> Slugs:
    """The slugs of every Band, Venue and Show in the database."""
    return assign(bands=db.query(Band.id, Band.name).all(), venues=db.query(Venue.id, Venue.name).all(),
                  shows=db.query(Show).options(selectinload(Show.acts)).all())
