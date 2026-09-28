from __future__ import annotations

from typing import Optional

import numpy as np
import strawberry
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from strawberry.types import Info

from app.embeddings.search import find_similar_bands, find_similar_shows
from app.graphql.types import ActType, BandType, ShowFilters, ShowType, VenueType
from app.models.act import Act
from app.models.band import Band
from app.models.show import Show, ShowStatus
from app.models.venue import Venue


# ── ORM → Strawberry type mappers ─────────────────────────────────────────────

def _venue(v: Venue) -> VenueType:
    return VenueType(
        id=v.id,
        name=v.name,
        address=v.address,
        city=v.city,
        region=v.region.value,
        website_url=v.website_url,
        latitude=v.latitude,
        longitude=v.longitude,
        timezone=v.timezone,
        phone=v.phone,
        google_rating=v.google_rating,
    )


def _band(b: Band) -> BandType:
    return BandType(
        id=b.id,
        name=b.name,
        genres=b.genres,
        spotify_url=b.spotify_url,
        soundcloud_url=b.soundcloud_url,
        bandcamp_url=b.bandcamp_url,
        description=b.description,
    )


def _act(a: Act) -> ActType:
    return ActType(position=a.position, band=_band(a.band))


def _show(s: Show) -> ShowType:
    return ShowType(
        id=s.id,
        date=s.date,
        door_time=s.door_time,
        set_time=s.set_time,
        venue=_venue(s.venue),
        acts=[_act(a) for a in s.acts],
        price_min=s.price_min,
        price_max=s.price_max,
        is_free=s.is_free,
        age_restriction=s.age_restriction.value,
        status=s.status.value,
        is_recommended=s.is_recommended,
        will_sell_out=s.will_sell_out,
        is_pit=s.is_pit,
        is_drink_tickets=s.is_drink_tickets,
        is_no_reentry=s.is_no_reentry,
        ticket_url=s.ticket_url,
        notes=s.notes,
    )


# ── query helpers ─────────────────────────────────────────────────────────────

def _query_shows(
    db: Session,
    filters: Optional[ShowFilters],
    limit: int,
    offset: int,
) -> list[Show]:
    f = filters or ShowFilters()

    q = db.query(Show).options(
        joinedload(Show.venue),
        joinedload(Show.acts).joinedload(Act.band),
    )

    # Status (default: upcoming)
    status_val = (f.status or "upcoming").lower()
    q = q.filter(Show.status == ShowStatus(status_val))

    if f.from_date:
        q = q.filter(Show.date >= f.from_date)
    if f.to_date:
        q = q.filter(Show.date <= f.to_date)

    if f.city:
        q = q.filter(
            Show.venue_id.in_(
                db.query(Venue.id).filter(func.lower(Venue.city) == f.city.lower())
            )
        )
    if f.region:
        q = q.filter(
            Show.venue_id.in_(
                db.query(Venue.id).filter(Venue.region == f.region)
            )
        )
    if f.band_name:
        q = q.filter(
            Show.id.in_(
                db.query(Act.show_id)
                .join(Act.band)
                .filter(Band.name.ilike(f"%{f.band_name}%"))
            )
        )
    if f.price_max is not None:
        q = q.filter(Show.price_min <= f.price_max)
    if f.is_free is not None:
        q = q.filter(Show.is_free == f.is_free)
    if f.age_restriction is not None:
        q = q.filter(Show.age_restriction == f.age_restriction)
    if f.is_recommended is not None:
        q = q.filter(Show.is_recommended == f.is_recommended)

    return q.order_by(Show.date).limit(limit).offset(offset).all()


# ── resolver ──────────────────────────────────────────────────────────────────

@strawberry.type
class Query:
    @strawberry.field
    def shows(
        self,
        info: Info,
        filters: Optional[ShowFilters] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ShowType]:
        db: Session = info.context["db"]
        return [_show(s) for s in _query_shows(db, filters, limit, offset)]

    @strawberry.field
    def show(self, info: Info, id: strawberry.ID) -> Optional[ShowType]:
        db: Session = info.context["db"]
        s = (
            db.query(Show)
            .options(
                joinedload(Show.venue),
                joinedload(Show.acts).joinedload(Act.band),
            )
            .filter(Show.id == int(id))
            .first()
        )
        return _show(s) if s else None

    @strawberry.field
    def bands(self, info: Info, query: str, limit: int = 20) -> list[BandType]:
        db: Session = info.context["db"]
        rows = (
            db.query(Band)
            .filter(Band.name.ilike(f"%{query}%"))
            .order_by(Band.name)
            .limit(limit)
            .all()
        )
        return [_band(b) for b in rows]

    @strawberry.field
    def band(self, info: Info, id: strawberry.ID) -> Optional[BandType]:
        db: Session = info.context["db"]
        b = db.query(Band).filter(Band.id == int(id)).first()
        return _band(b) if b else None

    @strawberry.field
    def similar_bands(
        self, info: Info, band_id: strawberry.ID, k: int = 10
    ) -> list[BandType]:
        db: Session = info.context["db"]
        band = db.query(Band).filter(Band.id == int(band_id)).first()
        if band is None:
            raise ValueError(f"Band {band_id} not found")
        if not band.embedding:
            return []
        embedding = np.frombuffer(band.embedding, dtype=np.float32)
        similar = find_similar_bands(embedding, k)
        ids = [bid for bid, _ in similar]
        rows = db.query(Band).filter(Band.id.in_(ids)).all()
        by_id = {b.id: b for b in rows}
        return [_band(by_id[bid]) for bid in ids if bid in by_id]

    @strawberry.field
    def similar_shows(
        self, info: Info, show_id: strawberry.ID, k: int = 10
    ) -> list[ShowType]:
        db: Session = info.context["db"]
        show = db.query(Show).filter(Show.id == int(show_id)).first()
        if show is None or not show.embedding:
            return []
        embedding = np.frombuffer(show.embedding, dtype=np.float32)
        similar = find_similar_shows(embedding, k)
        ids = [sid for sid, _ in similar]
        rows = (
            db.query(Show)
            .options(
                joinedload(Show.venue),
                joinedload(Show.acts).joinedload(Act.band),
            )
            .filter(Show.id.in_(ids), Show.status == ShowStatus.upcoming)
            .all()
        )
        by_id = {s.id: s for s in rows}
        return [_show(by_id[sid]) for sid in ids if sid in by_id]
