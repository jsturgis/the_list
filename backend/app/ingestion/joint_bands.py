"""Joint billings that arrive as one name: "Dying Fetus And Sanguisugabogg" is two Bands, but "Belle and
Sebastian" and "Tank And The Bangas" are one. MusicBrainz decides:

1. A name that isn't "<a> and/& <b>", or whose second half reads as part of the same act ("… & The Heavy
   Hitters", "… & Friends", "… And His Band"), is one Band.
2. If MusicBrainz knows the whole name as an artist, it's one Band.
3. If it knows both halves, and each half is a real match rather than a namesake (more than one word, or
   tagged with genres on MusicBrainz), it's two Bands. "Hare And Arrow" stays one: "Hare" and "Arrow" are
   on MusicBrainz, but as untagged one-word namesakes.
4. Otherwise it stays one Band, as it arrived.

Splitting is only ever done to names new to the database (at ingest), or by this module's one-off fix for
existing Bands:

Dry run by default:   python -m app.ingestion.joint_bands
Apply the changes:    python -m app.ingestion.joint_bands --apply
"""
from __future__ import annotations

import re
import sys
from typing import Callable, Optional

_JOINER = re.compile(r"\s+(?:and|&)\s+", re.IGNORECASE)
# A second half that belongs to the first: a backing band, "Friends", "His Band".
_SAME_ACT = re.compile(r"^(?:the|his|her|their|my|our)\b|^(?:friends|band|co\.?)$", re.IGNORECASE)

Search = Callable[[str], Optional[dict]]
Tagged = Callable[[dict], bool]


def joint_parts(name: str) -> list[str] | None:
    """The two names in "<a> and/& <b>", or None when it can't be a joint billing."""
    parts = [p.strip() for p in _JOINER.split(name.strip())]
    if len(parts) != 2 or not all(parts) or _SAME_ACT.search(parts[1]):
        return None
    return parts


def _mb_tagged(artist: dict) -> bool:
    """Whether a MusicBrainz artist has any tags (genres are a subset of tags)."""
    from app.pipeline.enrichment import _mb_lookup

    return bool(artist.get("tag-list") or _mb_lookup(artist["id"]).get("tag-list"))


def split_joint_name(name: str, search: Search | None = None, tagged: Tagged = _mb_tagged) -> list[str]:
    """[name] for one Band, or its two halves for a joint billing (see the module docstring)."""
    if search is None:
        from app.pipeline.enrichment import _mb_search as search
    parts = joint_parts(name)
    if parts is None or search(name):
        return [name]
    for part in parts:
        artist = search(part)
        if artist is None or (len(part.split()) == 1 and not tagged(artist)):
            return [name]
    return parts


def split_joint_acts(data: dict, split: Callable[[str], list[str]]) -> list[tuple[str, list[str]]]:
    """Split joint billings in one upsert-ready Show dict (bands, act notes, band enrichment) in place.

    Each half keeps the edition's genres and whether it's local; the link and image were for the billing
    as a whole, so they're dropped. An act note stays with the first half. Returns (name, halves) per split.
    """
    done = []
    bands, notes = list(data.get("bands") or []), list(data.get("act_notes") or [])
    notes += [None] * (len(bands) - len(notes))
    enrichment = dict(data.get("band_enrichment") or [])
    new_bands, new_notes, new_enrichment = [], [], []
    for name, note in zip(bands, notes):
        halves = split(name)
        if len(halves) > 1:
            done.append((name, halves))
        for i, half in enumerate(halves):
            new_bands.append(half)
            new_notes.append(note if i == 0 else None)
            e = enrichment.get(name, {})
            if len(halves) > 1:
                e = {"genres": list(e.get("genres") or []), "is_local": e.get("is_local")}
            new_enrichment.append((half, e))
    if done:
        data["bands"], data["act_notes"], data["band_enrichment"] = new_bands, new_notes, new_enrichment
    return done


# ── one-off fix for Bands already in the database ──────────────────────────────

def fix_joint_band_names(db, split: Callable[[str], list[str]] = split_joint_name, apply: bool = False) -> list[tuple[str, list[str], int]]:
    """Split existing joint-billing Bands into their halves, on every Show they're on.

    Each Act of the joint Band becomes Acts for both halves, side by side in the lineup (later Acts move down
    one). A half that's already a Band is reused; one that's new is created with no genres yet (the next
    lookup fills them). The joint Band is then deleted. Returns (name, halves, Shows affected) per fix.
    """
    from sqlalchemy import or_

    from app.models.act import Act
    from app.models.band import Band

    fixes = []
    candidates = db.query(Band).filter(or_(Band.name.ilike("% and %"), Band.name.ilike("% & %"))).order_by(Band.id)
    for band in candidates.all():
        if joint_parts(band.name) is None:
            continue
        halves = split(band.name)
        if len(halves) == 1:
            continue
        targets = []
        for half in halves:
            target = db.query(Band).filter(Band.name == half).first()
            if target is None:
                target = Band(name=half, genres=[], is_local=band.is_local)
                db.add(target)
                db.flush()
            targets.append(target)
        acts = list(band.acts)
        for act in acts:
            lineup = act.show.acts
            on_show = {a.band_id for a in lineup}
            for other in lineup:
                if other.position > act.position:
                    other.position += 1
            if targets[1].id not in on_show:
                db.add(Act(show_id=act.show_id, band_id=targets[1].id, position=act.position + 1))
            if targets[0].id in on_show:
                db.delete(act)  # the Show already lists the first half
            else:
                act.band = targets[0]
        db.flush()
        db.delete(band)
        db.flush()
        fixes.append((band.name, halves, len(acts)))

    if apply:
        db.commit()
    else:
        db.rollback()
    return fixes


def main(argv: list[str]) -> None:
    from app.database import SessionLocal

    apply = "--apply" in argv
    db = SessionLocal()
    try:
        fixes = fix_joint_band_names(db, apply=apply)
    finally:
        db.close()
    for name, halves, shows in fixes:
        print(f"{name!r} -> {' + '.join(repr(h) for h in halves)} ({shows} show{'s' * (shows != 1)})")
    print(f"{len(fixes)} joint Band name(s) {'split' if apply else 'would be split (dry run; --apply to change)'}")


if __name__ == "__main__":
    main(sys.argv[1:])
