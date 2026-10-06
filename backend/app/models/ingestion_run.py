from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IngestionStatus(str, enum.Enum):
    success = "success"
    failure = "failure"
    no_email = "no_email"


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus), nullable=False, default=IngestionStatus.success
    )

    # Email metadata
    email_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    email_subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    email_message_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Pipeline counts
    shows_parsed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shows_upserted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shows_new: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Bands first seen in this ingest (app/ingestion/ingest_stats.py): how many, and the percentage (0–100) with no
    # photo, and that had to fall back to the edition for their genres, photo and links. None without new Bands.
    new_bands: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_bands_without_photo_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_bands_photo_from_edition_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_bands_genres_from_edition_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_bands_links_from_edition_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Error details
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
