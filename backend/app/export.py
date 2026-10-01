"""Static JSON export: the data contract between the backend and the static frontend.

Writes four files to a directory:
  shows.json   Shows from today (Bay Area time) that aren't Past, each with `venueId` and
               `acts` as [bandId, position] (plus the act's note, when it has one)
  venues.json  Venues referenced by those Shows
  bands.json   Bands referenced by those Shows, each with up to six `similar` Band ids (exported only)
  meta.json    generation time, latest email subject, filter options, count of Upcoming Shows

Field names and values come from the GraphQL mappers (camelCased), so the export can't drift from
what the API returns.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime, time, timezone
from pathlib import Path

from sqlalchemy.orm import Session, joinedload
from strawberry.utils.str_converters import to_camel_case

from app import catalog
from app.clock import local_today
from app.graphql.queries import _band, _show, _venue
from app.models.act import Act
from app.models.show import Show, ShowStatus

SIMILAR_BANDS = 6


def _plain(value):
    """camelCase dict keys and ISO-format dates/times, recursively."""
    if isinstance(value, dict):
        return {to_camel_case(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, (date, time, datetime)):
        return value.isoformat()
    return value


def export(db: Session, out_dir: str | Path) -> dict[str, int]:
    """Write the four JSON files to `out_dir`; return how many records each holds."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    shows = (
        db.query(Show)
        .options(joinedload(Show.venue), joinedload(Show.acts).joinedload(Act.band))
        .filter(Show.date >= local_today(), Show.status != ShowStatus.past)
        .order_by(Show.date, Show.door_time, Show.id)
        .all()
    )
    venues = {s.venue.id: s.venue for s in shows}
    bands = {a.band.id: a.band for s in shows for a in s.acts}

    show_rows = []
    for s in shows:
        row = dataclasses.asdict(_show(s))
        del row["venue"], row["acts"]
        row["venue_id"] = s.venue_id
        row["acts"] = [[a.band_id, a.position] + ([a.note] if a.note else []) for a in s.acts]
        show_rows.append(row)

    band_rows = []
    for band in sorted(bands.values(), key=lambda b: b.id):
        row = dataclasses.asdict(_band(band))
        # Over-fetch so that dropping Bands outside the export still leaves up to six.
        row["similar"] = [bid for bid in catalog.similar_band_ids(db, band, k=SIMILAR_BANDS * 2)
                          if bid in bands][:SIMILAR_BANDS]
        band_rows.append(row)

    meta = {
        "generated_at": datetime.now(timezone.utc),
        "email_subject": catalog.latest_email_subject(db),
        "filter_options": dataclasses.asdict(catalog.filter_options(db)),
        "total_upcoming": sum(1 for s in shows if s.status == ShowStatus.upcoming),
    }

    files = {
        "shows": show_rows,
        "venues": [dataclasses.asdict(_venue(v)) for v in sorted(venues.values(), key=lambda v: v.id)],
        "bands": band_rows,
        "meta": meta,
    }
    for name, payload in files.items():
        (out / f"{name}.json").write_text(json.dumps(_plain(payload), ensure_ascii=False, separators=(",", ":")))
    return {name: len(payload) for name, payload in files.items() if isinstance(payload, list)}
