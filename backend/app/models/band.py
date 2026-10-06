from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, LargeBinary, String, Text, TypeDecorator, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JSONList(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return json.dumps(value or [])

    def process_result_value(self, value, dialect):
        return json.loads(value) if value else []


class JSONDict(TypeDecorator):
    """A JSON object, or NULL."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return json.dumps(value) if value else None

    def process_result_value(self, value, dialect):
        return json.loads(value) if value else None


class Band(Base):
    __tablename__ = "bands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    genres: Mapped[list] = mapped_column(JSONList, default=list)
    spotify_url: Mapped[Optional[str]] = mapped_column(String(500))
    soundcloud_url: Mapped[Optional[str]] = mapped_column(String(500))
    bandcamp_url: Mapped[Optional[str]] = mapped_column(String(500))
    # From the formatted edition
    website_url: Mapped[Optional[str]] = mapped_column(String(500))
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    # The photo's credit when it came from Wikimedia Commons: {author, license, license_url, source_url}; None for
    # the edition's photos. The site shows it with the photo, as the licence requires.
    image_credit: Mapped[Optional[dict]] = mapped_column(JSONDict)
    is_local: Mapped[Optional[bool]] = mapped_column(Boolean)
    # From the enriched export: what the Band is ("Bilingual metal band from Fairfield ...")
    description: Mapped[Optional[str]] = mapped_column(Text)
    # From MusicBrainz: every artist-to-URL relationship, as [{"type": "free streaming", "url": ...}]. Grouped
    # and ranked for the site by app/band_links.py.
    links: Mapped[list] = mapped_column(JSONList, default=list)
    # From Discogs: [{"name": ..., "active": bool}], current members marked active.
    members: Mapped[list] = mapped_column(JSONList, default=list)
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    acts: Mapped[List["Act"]] = relationship(back_populates="band")
