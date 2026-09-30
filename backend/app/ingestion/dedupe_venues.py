"""Merge Venues whose names differ only by case or a leading "the" (see upsert.venue_key).

Dry run by default:   python -m app.ingestion.dedupe_venues
Apply the merge:      python -m app.ingestion.dedupe_venues --apply
"""
from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ingestion.upsert import venue_key
from app.models.venue import Venue

# Detail fields copied onto the kept Venue when it's missing them.
_FILL_FIELDS = (
    "address", "website_url", "latitude", "longitude", "google_place_id",
    "timezone", "phone", "google_rating", "description", "wikipedia_url",
)


@dataclass
class VenueMerge:
    keep: Venue
    merged: list[Venue]
    shows_moved: int


def merge_duplicate_venues(db: Session, apply: bool = False) -> list[VenueMerge]:
    """Merge each group of duplicate Venues into the one with the most Shows (lowest id on ties).

    Moves Shows to the kept Venue and fills its empty detail fields from the duplicates.
    Commits only when `apply` is true.
    """
    groups: dict[str, list[Venue]] = defaultdict(list)
    for v in db.query(Venue).order_by(Venue.id):
        groups[venue_key(v.name)].append(v)

    merges: list[VenueMerge] = []
    for venues in groups.values():
        if len(venues) < 2:
            continue
        keep = max(venues, key=lambda v: (len(v.shows), -v.id))
        dups = [v for v in venues if v is not keep]
        moved = 0
        for dup in dups:
            for field in _FILL_FIELDS:
                if getattr(keep, field) is None and getattr(dup, field) is not None:
                    setattr(keep, field, getattr(dup, field))
            # Move through the relationship: a bulk UPDATE would leave dup.shows stale, and
            # deleting dup would then null out those Shows' venue_id.
            for show in list(dup.shows):
                show.venue = keep
                moved += 1
            db.delete(dup)
        merges.append(VenueMerge(keep=keep, merged=dups, shows_moved=moved))

    if apply:
        db.commit()
    else:
        db.rollback()
    return merges


def main(argv: list[str]) -> None:
    from app.database import SessionLocal

    apply = "--apply" in argv
    db = SessionLocal()
    try:
        merges = merge_duplicate_venues(db, apply=apply)
        for m in merges:
            names = ", ".join(f"{v.id}:{v.name!r}" for v in m.merged)
            print(f"keep {m.keep.id}:{m.keep.name!r} <- {names} ({m.shows_moved} shows moved)")
        verb = "Merged" if apply else "Would merge"
        print(f"{verb} {sum(len(m.merged) for m in merges)} duplicate venues into {len(merges)}.")
        if not apply and merges:
            print("Dry run: nothing changed. Re-run with --apply to merge.")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
