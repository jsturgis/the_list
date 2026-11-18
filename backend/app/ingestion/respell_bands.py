"""Put right the names of stored Bands listed misspelt, as new ones are at ingest (app/ingestion/spelling.py).

A stored Band no service has under its name ("Sunamo") is renamed to the close name a service does have ("Sunami"),
keeping the listed one in Band.spellings, and marked to be looked up again (the backfill does: its genres, links and
photo come with the right name). When a Band with the right name is stored already, the misspelt one is merged into
it (app/ingestion/dedupe_bands.py merge_band).

    python -m app.cli respell-bands [--name "Sunamo" ...] [--apply]

Without names, the Bands on Upcoming Shows with nothing from the services (no MusicBrainz links, no Discogs members).
Dry run without --apply. The Backfill workflow runs it (its `respell` input) before looking Bands up.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.clock import local_today
from app.ingestion.dedupe_bands import merge_band
from app.ingestion.spelling import Respelling
from app.ingestion.upsert import find_band
from app.models.act import Act
from app.models.band import Band
from app.models.show import Show, ShowStatus

logger = logging.getLogger(__name__)


@dataclass
class Respelt:
    listed: str
    fixed: str
    band_id: int
    merged_into: int | None = None   # the stored Band it was merged into, when there was one

    def __str__(self) -> str:
        into = f", merged into band {self.merged_into}" if self.merged_into else ""
        return f"{self.listed!r} -> {self.fixed!r} (band {self.band_id}{into})"


def candidates(db: Session, names: list[str] | None = None) -> list[Band]:
    """The stored Bands to check: these names', else those on Upcoming Shows with nothing from the services."""
    if names:
        return [band for band in (find_band(db, name) for name in names) if band]
    today = local_today()
    bands = (db.query(Band).join(Act).join(Show)
             .filter(Show.date >= today, Show.status == ShowStatus.upcoming).distinct().order_by(Band.id).all())
    return [band for band in bands if not band.links and not band.members]


def respell_stored(db: Session, bands: list[Band], matched: Callable[[str], bool],
                   respell: Callable[[str], Respelling | None], apply: bool = False) -> list[Respelt]:
    """Rename (or merge) each of `bands` that no service has under its name (`matched` is False) and that `respell`
    puts right. Commits only with `apply`."""
    done: list[Respelt] = []
    for band in bands:
        listed = band.name
        if matched(listed):
            continue
        fixed = respell(listed)
        if fixed is None:
            continue
        stored = find_band(db, fixed.name)
        if stored is not None and stored.id != band.id:
            stored.spellings = list(dict.fromkeys([*(stored.spellings or []), listed]))
            done.append(Respelt(listed, stored.name, band.id, stored.id))
            merge_band(db, stored, band)
        else:
            band.spellings = list(dict.fromkeys([*(band.spellings or []), listed]))
            band.name = fixed.name
            band.enriched_at = None   # looked up again under its name (the backfill)
            done.append(Respelt(listed, fixed.name, band.id))
        db.flush()
    if apply:
        db.commit()
    else:
        db.rollback()
    return done
