import enum
from datetime import date, datetime, time

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
    door_time: Mapped[time | None] = mapped_column(Time)
    set_time: Mapped[time | None] = mapped_column(Time)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    price_min: Mapped[float | None] = mapped_column(Float)
    price_max: Mapped[float | None] = mapped_column(Float)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False)
    age_restriction: Mapped[AgeRestriction] = mapped_column(Enum(AgeRestriction), default=AgeRestriction.unknown)
    status: Mapped[ShowStatus] = mapped_column(Enum(ShowStatus), default=ShowStatus.upcoming, index=True)
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=False)    # * Steve's Pick
    will_sell_out: Mapped[bool] = mapped_column(Boolean, default=False)     # $
    is_pit: Mapped[bool] = mapped_column(Boolean, default=False)            # @ pit warning
    is_drink_tickets: Mapped[bool] = mapped_column(Boolean, default=False)  # ^ under-21 drink tickets
    is_no_reentry: Mapped[bool] = mapped_column(Boolean, default=False)     # # no ins/outs
    ticket_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    venue: Mapped["Venue"] = relationship(back_populates="shows")
    acts: Mapped[list["Act"]] = relationship(
        back_populates="show", order_by="Act.position", cascade="all, delete-orphan"
    )
