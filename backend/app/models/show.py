from __future__ import annotations

import enum
from datetime import date, datetime, time
from typing import List, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, Float, ForeignKey,
    LargeBinary, String, Text, Time, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgeRestriction(str, enum.Enum):
    all_ages = "a/a"
    plus_5 = "5+"
    plus_6 = "6+"
    plus_8 = "8+"
    plus_12 = "12+"
    plus_13 = "13+"
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
    # Read from the listing (app/ingestion/steve_list.py): doors before 5pm, "(sold out)", a benefit or fundraiser.
    # The ticket fields, the cause and the special event are from the formatted editions ingested until November
    # 2026; the List itself doesn't have them.
    is_matinee: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sold_out: Mapped[bool] = mapped_column(Boolean, default=False)
    ticket_provider: Mapped[Optional[str]] = mapped_column(String(100))
    ticket_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_benefit: Mapped[bool] = mapped_column(Boolean, default=False)
    benefit_cause: Mapped[Optional[str]] = mapped_column(String(255))
    special_event: Mapped[Optional[str]] = mapped_column(String(255))
    # From the Venue's own calendar (app/ingestion/venue_calendar.py): a stored path (as Band.image_url) or a
    # remote URL not yet downloaded, a link to the Show's own page on the Venue's site, and (when Steve's edition
    # has none) a ticket link. Never overwrites what the edition already gave the Show.
    flyer_image_url: Mapped[Optional[str]] = mapped_column(String(500))
    more_info_url: Mapped[Optional[str]] = mapped_column(String(500))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    # Where the Show comes from: "list" (Steve's List), or the event page it was added from by hand
    # (`python -m app.cli add-event`), e.g. "ticketweb". The List wins: once Steve lists it, it's the List's.
    source: Mapped[str] = mapped_column(String(20), default="list", server_default="list")
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    venue: Mapped["Venue"] = relationship(back_populates="shows")
    acts: Mapped[List["Act"]] = relationship(
        back_populates="show", order_by="Act.position", cascade="all, delete-orphan"
    )
