"""Merge Bands stored twice under different spellings: names with the same key (see upsert.band_key), like
"Swept To Sea" and "Swept to Sea", or "B.F.H" and "B.F.H.".

Dry run by default:   python -m app.ingestion.dedupe_bands
Apply the merge:      python -m app.ingestion.dedupe_bands --apply
"""
from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import parse_qs

from sqlalchemy.orm import Session

from app.ingestion.upsert import band_key
from app.models.band import Band


# Details the kept Band takes from a duplicate when it has none of its own. A photo goes with its credit and focal
# point (_PHOTO_FIELDS), so a credit never ends up on another photo.
_FILL_FIELDS = (
    "genres", "spotify_url", "soundcloud_url", "bandcamp_url", "website_url", "is_local", "description", "links",
    "members", "embedding", "enriched_at",
)
_PHOTO_FIELDS = ("image_url", "image_credit", "image_focus")


def _empty(value) -> bool:
    """None, or an empty list or string; False is a value (a Band that isn't local)."""
    return value is None or value in ([], "")


@dataclass
class BandMerge:
    keep: Band
    merged: list[Band]
    # Captured before commit/rollback, which expires the ORM objects.
    merged_ids: list[int]
    summary: str


def merge_duplicate_bands(db: Session, apply: bool = False) -> list[BandMerge]:
    """Merge each group of Bands sharing a key into the one with the most Acts (then one that's been enriched, then
    the lowest id), which keeps its name; the others' Acts move to it. Commits only when `apply` is true.
    """
    groups: dict[str, list[Band]] = defaultdict(list)
    for band in db.query(Band).order_by(Band.id):
        if key := band_key(band.name):
            groups[key].append(band)

    merges: list[BandMerge] = []
    for bands in groups.values():
        if len(bands) < 2:
            continue
        keep = max(bands, key=lambda b: (len(b.acts), b.enriched_at is not None, -b.id))
        dups = [b for b in bands if b is not keep]
        summary = f"keep {keep.id}:{keep.name!r} <- " + ", ".join(f"{d.id}:{d.name!r}" for d in dups)
        kept_acts = {a.show_id: a for a in keep.acts}
        for dup in dups:
            for field in _FILL_FIELDS:
                if _empty(getattr(keep, field)) and not _empty(getattr(dup, field)):
                    setattr(keep, field, getattr(dup, field))
            if not keep.image_url and dup.image_url:
                for field in _PHOTO_FIELDS:
                    setattr(keep, field, getattr(dup, field))
            for act in list(dup.acts):
                same = kept_acts.get(act.show_id)
                if same is None:
                    act.band = keep
                    kept_acts[act.show_id] = act
                    continue
                # The Show lists both spellings: one Act, where the first of them was, and the lineup closed up.
                show = act.show
                same.position = min(same.position, act.position)
                db.delete(act)
                db.flush()
                for position, a in enumerate(sorted((a for a in show.acts if a is not act), key=lambda a: a.position)):
                    a.position = position
            db.flush()
            db.delete(dup)
        merges.append(BandMerge(keep=keep, merged=dups, merged_ids=[d.id for d in dups], summary=summary))

    if apply:
        db.commit()
    else:
        db.rollback()
    return merges


def saved_filters_pinning(band_ids: set[int], saved_filters: list[dict]) -> list[dict]:
    """The Saved Filters (Supabase `saved_filters` rows) that pin one of these Bands (`bandId=…`). A merged-away
    Band's id no longer matches any Show, so these need pointing at the kept Band by hand."""
    def pinned(query: str) -> int | None:
        value = parse_qs(query).get("bandId", [""])[0]
        return int(value) if value.isdigit() else None

    return [row for row in saved_filters if pinned(row["query"]) in band_ids]


def main(argv: list[str]) -> None:
    from app.alerts import SupabaseError, fetch_saved_filters
    from app.database import SessionLocal
    from app.embeddings.indexer import BAND_INDEX_PATH, remove_from_index

    apply = "--apply" in argv
    db = SessionLocal()
    try:
        merges = merge_duplicate_bands(db, apply=apply)
        for m in merges:
            print(m.summary)
        merged_ids = {i for m in merges for i in m.merged_ids}
        verb = "Merged" if apply else "Would merge"
        print(f"{verb} {len(merged_ids)} duplicate bands into {len(merges)}.")
        if apply and merged_ids:
            # Merged-away Bands would otherwise still come up as Similar Bands.
            remove_from_index(BAND_INDEX_PATH, sorted(merged_ids))
        try:
            for row in saved_filters_pinning(merged_ids, fetch_saved_filters()):
                print(f"Saved Filter {row['name']!r} (user {row['user_id']}) pins merged band: {row['query']}")
        except SupabaseError as exc:
            print(f"Couldn't check Saved Filters for merged bands: {exc}")
        if not apply and merges:
            print("Dry run: nothing changed. Re-run with --apply to merge.")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
