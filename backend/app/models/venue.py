from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.band import JSONDict


class Region(str, enum.Enum):
    sf = "sf"
    east_bay = "east_bay"
    north_bay = "north_bay"
    south_bay = "south_bay"
    santa_cruz = "santa_cruz"


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    address: Mapped[Optional[str]] = mapped_column(String(500))
    city: Mapped[str] = mapped_column(String(100))
    region: Mapped[Region] = mapped_column(Enum(Region))
    website_url: Mapped[Optional[str]] = mapped_column(String(500))
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    google_place_id: Mapped[Optional[str]] = mapped_column(String(255))
    timezone: Mapped[Optional[str]] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    google_rating: Mapped[Optional[float]] = mapped_column(Float)
    description: Mapped[Optional[str]] = mapped_column(Text)
    wikipedia_url: Mapped[Optional[str]] = mapped_column(String(500))
    # From the formatted editions ingested until November 2026; the List itself doesn't have these
    neighborhood: Mapped[Optional[str]] = mapped_column(String(255))
    venue_type: Mapped[Optional[str]] = mapped_column(String(100))
    nearest_transit: Mapped[Optional[str]] = mapped_column(String(255))
    instagram: Mapped[Optional[str]] = mapped_column(String(100))
    # The Venue's photo: a stored file in the images folder (app/ingestion/venue_photos.py), or a remote URL
    # still to be downloaded, which the site never shows.
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    # Who took a Wikimedia Commons photo and its licence (author, license, license_url, source_url), which the
    # licence requires the site to show; None for a photo from anywhere else.
    image_credit: Mapped[Optional[dict]] = mapped_column(JSONDict)
    default_age_restriction: Mapped[Optional[str]] = mapped_column(String(50))
    is_sober_space: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_cash_only: Mapped[Optional[bool]] = mapped_column(Boolean)
    membership_required: Mapped[Optional[bool]] = mapped_column(Boolean)
    # The Venue's own calendar page, found by app/ingestion/venue_calendar.py (or set by a correction,
    # app/ingestion/venue_corrections.py). calendar_checked_at is when it was last looked for with a definite
    # answer (found, or none), looked for again after 30 days; None means not yet. calendar_read_at is when the
    # page was last read. calendar_retry_at holds the Venue back after a temporary failure (the site or the LLM
    # didn't answer). `python -m app.cli backfill --recheck-calendars` clears all three to force another try.
    calendar_url: Mapped[Optional[str]] = mapped_column(String(500))
    calendar_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    calendar_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    calendar_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    shows: Mapped[List["Show"]] = relationship(back_populates="venue")
