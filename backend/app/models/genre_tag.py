from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GenreTag(Base):
    """Whether a tag outside the genre vocabulary is a genre, as judged once (app/ingestion/genre_filter.py)."""

    __tablename__ = "genre_tags"

    # The tag ignoring case, spacing and punctuation (genre_filter.key); `example` is how it was first written.
    tag: Mapped[str] = mapped_column(String, primary_key=True)
    example: Mapped[str] = mapped_column(String, nullable=False)
    is_genre: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # The model's probability that it's a genre; None for a decision made by hand.
    score: Mapped[Optional[float]] = mapped_column(Float)
    decided_by: Mapped[str] = mapped_column(String, nullable=False)  # "model" or "hand"
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
