from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
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

    # Error details
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
