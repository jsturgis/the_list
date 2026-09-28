from __future__ import annotations

import enum
from datetime import date, datetime, time
from typing import List, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, Float, ForeignKey,
    LargeBinary, String, Text, Time, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgeRestriction(str, enum.Enum):
    all_ages = "a/a"
    plus_5 = "5+"
    plus_6 = "6+"
    plus_12 = "12+"
    plus_16 = "16+"
    plus_18 = "18+"
    plus_21 = "21+"
    unknown = "unknown"


class ShowStatus(str, enum.Enum):
    upcoming = "upcoming"
    past = "past"
    cancelled = "cancelled"
    postponed = "postponed"


class Show(Base):
    __tablename__ = "shows"
    __table_args__ = (
        UniqueConstraint("date", "venue_id", "door_time", name="uq_show_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    door_time: Mapped[Optional[time]] = mapped_column(Time)
    set_time: Mapped[Optional[time]] = mapped_column(Time)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    price_min: Mapped[Optional[float]] = mapped_column(Float)
    price_max: Mapped[Optional[float]] = mapped_column(Float)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False)
    age_restriction: Mapped[AgeRestriction] = mapped_column(Enum(AgeRestriction), default=AgeRestriction.unknown)
    status: Mapped[ShowStatus] = mapped_column(Enum(ShowStatus), default=ShowStatus.upcoming, index=True)
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    will_sell_out: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pit: Mapped[bool] = mapped_column(Boolean, default=False)
    is_drink_tickets: Mapped[bool] = mapped_column(Boolean, default=False)
    is_no_reentry: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    venue: Mapped["Venue"] = relationship(back_populates="shows")
    acts: Mapped[List["Act"]] = relationship(
        back_populates="show", order_by="Act.position", cascade="all, delete-orphan"
    )
