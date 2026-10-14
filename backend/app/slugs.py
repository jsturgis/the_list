"""Page slugs: the names in the site's Band, Venue and Show page URLs (/bands/deafheaven/).

Derived from the current names each time they're needed, never stored: the export writes them for the site and the
Alert emails link with them. Each is unique among every Band (Venue, Show) in the database, not only those exported,
so a slug doesn't move to another Band as Shows come and go. A renamed Band gets a new slug; its numeric URL
(/bands/12/) redirects to whatever the slug is now, so that's the permanent link.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.band import Band


@dataclass(frozen=True)
class Slugs:
    bands: dict[int, str] = field(default_factory=dict)


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


def assign(bands: Iterable = ()) -> Slugs:
    return Slugs(bands=_unique({b.id: _wanted("band", b.id, b.name) for b in bands}))


def site_slugs(db: Session) -> Slugs:
    """The slugs of every Band in the database."""
    return assign(bands=db.query(Band.id, Band.name).all())
