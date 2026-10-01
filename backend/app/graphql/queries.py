from __future__ import annotations

from typing import Optional

import numpy as np
import strawberry
from sqlalchemy import Text, cast, func
from sqlalchemy.orm import Session, joinedload
from strawberry.types import Info

from app import catalog
from app.clock import local_today
from app.embeddings.search import find_similar_shows
from app.fuzzy_search import matches_search
from app.graphql.types import (
    ActType, BandType, FilterOptionsType, IngestionRunType, ShowFilters, ShowType, VenueType,
)
from app.models.act import Act
from app.models.band import Band
from app.models.ingestion_run import IngestionRun, IngestionStatus
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
        google_place_id=v.google_place_id,
        description=v.description,
        wikipedia_url=v.wikipedia_url,
        neighborhood=v.neighborhood,
        venue_type=v.venue_type,
        nearest_transit=v.nearest_transit,
        instagram=v.instagram,
        image_url=v.image_url,
        default_age_restriction=v.default_age_restriction,
        is_sober_space=v.is_sober_space,
        is_cash_only=v.is_cash_only,
        membership_required=v.membership_required,
    )


def _band(b: Band) -> BandType:
    return BandType(
        id=b.id,
        name=b.name,
        genres=b.genres,
        spotify_url=b.spotify_url,
        soundcloud_url=b.soundcloud_url,
        bandcamp_url=b.bandcamp_url,
        website_url=b.website_url,
        image_url=b.image_url,
        is_local=b.is_local,
    )


def _act(a: Act) -> ActType:
    return ActType(position=a.position, band=_band(a.band), note=a.note)


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
        notes=s.notes,
        is_matinee=bool(s.is_matinee),
        is_sold_out=bool(s.is_sold_out),
        ticket_provider=s.ticket_provider,
        ticket_url=s.ticket_url,
        is_benefit=bool(s.is_benefit),
        benefit_cause=s.benefit_cause,
        special_event=s.special_event,
    )


# ── query helpers ─────────────────────────────────────────────────────────────

def _ingestion_run(r: IngestionRun) -> IngestionRunType:
    return IngestionRunType(
        id=r.id,
        started_at=r.started_at,
        finished_at=r.finished_at,
        status=r.status.value,
        email_received_at=r.email_received_at,
        email_subject=r.email_subject,
        email_message_id=r.email_message_id,
        shows_parsed=r.shows_parsed,
        shows_upserted=r.shows_upserted,
        shows_new=r.shows_new,
        error=r.error,
    )


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
    if status_val == "upcoming":
        q = q.filter(Show.date >= local_today())

    if f.from_date:
        q = q.filter(Show.date >= f.from_date)
    if f.to_date:
        q = q.filter(Show.date <= f.to_date)

    if f.venue_id is not None:
        q = q.filter(Show.venue_id == f.venue_id)
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
    if f.band_id is not None:
        q = q.filter(
            Show.id.in_(
                db.query(Act.show_id).filter(Act.band_id == f.band_id)
            )
        )
    elif f.band_name:
        q = q.filter(
            Show.id.in_(
                db.query(Act.show_id)
                .join(Act.band)
                .filter(Band.name.ilike(f"%{f.band_name}%"))
            )
        )
    if f.venue_name:
        q = q.filter(
            Show.venue_id.in_(
                db.query(Venue.id).filter(Venue.name.ilike(f"%{f.venue_name}%"))
            )
        )
    if f.genre:
        genre_match_ids = (
            db.query(Act.show_id)
            .join(Act.band)
            .filter(cast(Band.genres, Text).like(f"%{f.genre}%"))
        )
        q = q.filter(Show.id.in_(genre_match_ids))
    if f.price_max is not None:
        q = q.filter(Show.price_min <= f.price_max)
    if f.is_free is not None:
        q = q.filter(Show.is_free == f.is_free)
    if f.age_restriction is not None:
        q = q.filter(Show.age_restriction == f.age_restriction)
    if f.is_recommended is not None:
        q = q.filter(Show.is_recommended == f.is_recommended)

    q = q.order_by(Show.date)
    if f.search and f.search.strip():
        # SQLite can't do typo-tolerant matching, so filter in Python before paginating.
        matched = [
            s for s in q.all()
            if matches_search(f.search, [s.venue.name, *(a.band.name for a in s.acts)])
        ]
        return matched[offset:offset + limit]
    return q.limit(limit).offset(offset).all()


# ── resolver ──────────────────────────────────────────────────────────────────

@strawberry.type
class Query:
    @strawberry.field
    def shows(
        self,
        info: Info,
        filters: Optional[ShowFilters] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ShowType]:
        db: Session = info.context["db"]
        return [_show(s) for s in _query_shows(db, filters, limit, offset)]

    @strawberry.field
    def filter_options(self, info: Info) -> FilterOptionsType:
        opts = catalog.filter_options(info.context["db"])
        return FilterOptionsType(regions=opts.regions, ages=opts.ages, genres=opts.genres, dates=opts.dates)

    @strawberry.field
    def show_count(
        self,
        info: Info,
        filters: Optional[ShowFilters] = None,
    ) -> int:
        db: Session = info.context["db"]
        f = filters or ShowFilters()
        status_val = (f.status or "upcoming").lower()
        q = db.query(func.count(Show.id)).filter(Show.status == ShowStatus(status_val))
        if status_val == "upcoming":
            q = q.filter(Show.date >= local_today())
        return q.scalar() or 0

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
    def venue(self, info: Info, id: strawberry.ID) -> Optional[VenueType]:
        db: Session = info.context["db"]
        v = db.query(Venue).filter(Venue.id == int(id)).first()
        return _venue(v) if v else None

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
        ids = catalog.similar_band_ids(db, band, k)
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

    @strawberry.field
    def ingestion_runs(
        self, info: Info, limit: int = 20, status: Optional[str] = None
    ) -> list[IngestionRunType]:
        """Pipeline runs, newest first. `status` is one of success | failure | no_email."""
        db: Session = info.context["db"]
        q = db.query(IngestionRun)
        if status is not None:
            q = q.filter(IngestionRun.status == IngestionStatus(status))
        rows = q.order_by(IngestionRun.started_at.desc()).limit(limit).all()
        return [_ingestion_run(r) for r in rows]
