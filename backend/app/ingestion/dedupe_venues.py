"""Merge duplicate Venues: names that differ only by case or a leading "the" (see upsert.venue_key),
or records that resolve to the same Google place.

Dry run by default:   python -m app.ingestion.dedupe_venues
Apply the merge:      python -m app.ingestion.dedupe_venues --apply
"""
from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ingestion.parser import split_venue_street
from app.ingestion.upsert import venue_key
from app.models.venue import Venue

# Detail fields copied onto the kept Venue when it's missing them.
_FILL_FIELDS = (
    "address", "website_url", "latitude", "longitude", "google_place_id",
    "timezone", "phone", "google_rating", "description", "wikipedia_url",
)


@dataclass
class VenueRename:
    venue: Venue
    old_name: str


@dataclass
class VenueMerge:
    keep: Venue
    merged: list[Venue]
    shows_moved: int
    shows_combined: int  # listed under both Venues on the same date/door time; folded into one
    summary: str = ""    # captured before commit/rollback, which expires the ORM objects


def strip_street_from_names(db: Session) -> list[VenueRename]:
    """Remove a street address from Venue names ("Felton Music Hall, 6275 Hwy 9")."""
    renames = []
    for v in db.query(Venue).order_by(Venue.id):
        name, _street = split_venue_street(v.name)
        if name != v.name:
            renames.append(VenueRename(v, v.name))
            v.name = name
    return renames


def merge_duplicate_venues(db: Session, apply: bool = False) -> list[VenueMerge]:
    """Merge each group of duplicate Venues into the one with the most Shows (lowest id on ties).

    Moves Shows to the kept Venue and fills its empty detail fields from the duplicates.
    Commits only when `apply` is true.
    """
    venues_all = db.query(Venue).order_by(Venue.id).all()

    # Union-find over Venue ids: join Venues sharing a name key or a Google place ID.
    parent = {v.id: v.id for v in venues_all}

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(ids: list[int]) -> None:
        for i in ids[1:]:
            parent[root(i)] = root(ids[0])

    by_place: dict[str, list[int]] = defaultdict(list)
    by_name: dict[tuple[str, str], list[Venue]] = defaultdict(list)
    for v in venues_all:
        if v.google_place_id:
            by_place[v.google_place_id].append(v.id)
        by_name[(venue_key(v.name), v.region.value)].append(v)
    for ids in by_place.values():
        join(ids)
    # Same name in the same Region is one Venue, unless Google says they're different places.
    for group in by_name.values():
        if len({v.google_place_id for v in group if v.google_place_id}) <= 1:
            join([v.id for v in group])

    groups: dict[int, list[Venue]] = defaultdict(list)
    for v in venues_all:
        groups[root(v.id)].append(v)

    merges: list[VenueMerge] = []
    for venues in groups.values():
        if len(venues) < 2:
            continue
        keep = max(venues, key=lambda v: (len(v.shows), -v.id))
        dups = [v for v in venues if v is not keep]
        summary = f"keep {keep.id}:{keep.name!r} <- " + ", ".join(f"{d.id}:{d.name!r}" for d in dups)
        kept_shows = {(s.date, s.door_time): s for s in keep.shows}
        moved = combined = 0
        for dup in dups:
            for field in _FILL_FIELDS:
                if getattr(keep, field) is None and getattr(dup, field) is not None:
                    setattr(keep, field, getattr(dup, field))
            # Move through the relationship: a bulk UPDATE would leave dup.shows stale, and
            # deleting dup would then null out those Shows' venue_id.
            for show in list(dup.shows):
                same = kept_shows.get((show.date, show.door_time))
                if same is None:
                    show.venue = keep
                    kept_shows[(show.date, show.door_time)] = show
                    moved += 1
                    continue
                # The same Show listed under both names: keep one, adding any Bands it lacks.
                have = {a.band_id for a in same.acts}
                for act in list(show.acts):
                    if act.band_id not in have:
                        act.position = len(same.acts)
                        act.show = same
                        have.add(act.band_id)
                db.delete(show)
                combined += 1
            db.flush()
            db.delete(dup)
        merges.append(VenueMerge(
            keep=keep, merged=dups, shows_moved=moved, shows_combined=combined,
            summary=f"{summary} ({moved} shows moved, {combined} combined)",
        ))

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
        renames = strip_street_from_names(db)
        for r in renames:
            print(f"rename {r.venue.id}: {r.old_name!r} -> {r.venue.name!r}")
        merges = merge_duplicate_venues(db, apply=apply)
        for m in merges:
            print(m.summary)
        verb = "Merged" if apply else "Would merge"
        print(f"{verb} {sum(len(m.merged) for m in merges)} duplicate venues into {len(merges)}.")
        if not apply and merges:
            print("Dry run: nothing changed. Re-run with --apply to merge.")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
