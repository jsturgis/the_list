from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IngestionStatus(str, enum.Enum):
    success = "success"
    failure = "failure"


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus), nullable=False, default=IngestionStatus.success
    )

    # The List as this run found it (app/ingestion/steve_list.py): the date in its header, what the site calls that
    # edition, and the page's SHA-256. The hash is set once the page's Shows are stored, and is how the hourly
    # check tells a changed page; runs from before the List was read from Steve's page have none.
    edition_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    edition_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Pipeline counts
    shows_parsed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shows_upserted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shows_new: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Venues first seen in this ingest. None for runs from before it was counted.
    new_venues: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Bands first seen in this ingest (app/ingestion/ingest_stats.py): how many, and the percentage (0–100) with no
    # photo. None without new Bands.
    new_bands: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_bands_without_photo_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Error details
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
