"""Fix Band names that include a set time or show details, e.g. "The Coverups (2:30pm)" or
"Brassica a/a $20 8pm" (see parser.clean_band_name).

Each bad Band is merged into an existing Band with the cleaned name, or renamed if there is none.

Dry run by default:   python -m app.ingestion.clean_band_names
Apply the changes:    python -m app.ingestion.clean_band_names --apply
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ingestion.parser import clean_band_name
from app.models.band import Band


@dataclass
class BandFix:
    old_name: str
    new_name: str
    merged_into_existing: bool


def clean_band_names(db: Session, apply: bool = False) -> list[BandFix]:
    fixes: list[BandFix] = []
    for band in db.query(Band).order_by(Band.id).all():
        clean = clean_band_name(band.name)
        if clean == band.name:
            continue
        target = db.query(Band).filter(Band.name == clean, Band.id != band.id).first()
        if target is None:
            fixes.append(BandFix(band.name, clean, merged_into_existing=False))
            band.name = clean
            continue
        fixes.append(BandFix(band.name, clean, merged_into_existing=True))
        target_show_ids = {a.show_id for a in target.acts}
        for act in list(band.acts):
            if act.show_id in target_show_ids:
                db.delete(act)  # the Show already lists the real Band
            else:
                act.band = target
        db.flush()
        db.delete(band)

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
        fixes = clean_band_names(db, apply=apply)
        for f in fixes:
            how = "merge into existing" if f.merged_into_existing else "rename to"
            print(f"{f.old_name!r}: {how} {f.new_name!r}")
        print(f"{'Fixed' if apply else 'Would fix'} {len(fixes)} band names.")
        if not apply and fixes:
            print("Dry run: nothing changed. Re-run with --apply to apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
