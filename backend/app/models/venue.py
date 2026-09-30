from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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
    # From the formatted edition
    neighborhood: Mapped[Optional[str]] = mapped_column(String(255))
    venue_type: Mapped[Optional[str]] = mapped_column(String(100))
    nearest_transit: Mapped[Optional[str]] = mapped_column(String(255))
    instagram: Mapped[Optional[str]] = mapped_column(String(100))
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    default_age_restriction: Mapped[Optional[str]] = mapped_column(String(50))
    is_sober_space: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_cash_only: Mapped[Optional[bool]] = mapped_column(Boolean)
    membership_required: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    shows: Mapped[List["Show"]] = relationship(back_populates="venue")
