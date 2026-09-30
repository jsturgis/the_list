"""Read-only catalog queries shared by the GraphQL API and the static export."""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session, joinedload

from app.clock import local_today
from app.embeddings.search import find_similar_bands
from app.models.act import Act
from app.models.band import Band
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.models.show import Show, ShowStatus


@dataclass
class FilterOptions:
    regions: list[str]
    ages: list[str]
    genres: list[str]
    dates: list[str]


def filter_options(db: Session) -> FilterOptions:
    """Distinct Regions, ages, genres and dates across Upcoming Shows from today (Bay Area time)."""
    upcoming = (
        db.query(Show)
        .options(joinedload(Show.venue), joinedload(Show.acts).joinedload(Act.band))
        .filter(Show.status == ShowStatus.upcoming, Show.date >= local_today())
        .all()
    )

    regions, ages, genres, dates = set(), set(), set(), set()
    for show in upcoming:
        if show.venue.region:
            regions.add(show.venue.region.value)
        if show.age_restriction and show.age_restriction.value != "unknown":
            ages.add(show.age_restriction.value)
        dates.add(str(show.date))
        for act in show.acts:
            band_genres = act.band.genres
            genres.update(json.loads(band_genres) if isinstance(band_genres, str) else band_genres)

    def age_key(age: str) -> int:
        return 0 if age == "a/a" else int(age.rstrip("+"))

    return FilterOptions(
        regions=sorted(regions),
        ages=sorted(ages, key=age_key),
        genres=sorted(genres),
        dates=sorted(dates),
    )


def similar_band_ids(db: Session, band: Band, k: int) -> list[int]:
    """Ids of up to k Bands most similar to `band`, nearest first, never including `band` itself."""
    if not band.embedding:
        return []
    embedding = np.frombuffer(band.embedding, dtype=np.float32)
    # The Band is its own nearest neighbour; fetch one extra and drop it.
    similar = find_similar_bands(embedding, k + 1)
    return [bid for bid, _ in similar if bid != band.id][:k]


def latest_email_subject(db: Session) -> str | None:
    """Subject of the email from the most recent successful ingestion run."""
    run = (
        db.query(IngestionRun)
        .filter(IngestionRun.status == IngestionStatus.success)
        .order_by(IngestionRun.started_at.desc())
        .first()
    )
    return run.email_subject if run else None
