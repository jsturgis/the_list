"""Embedding generation and FAISS indexing helpers."""
from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from app.embeddings.client import embed
from app.embeddings.indexer import (
    BAND_INDEX_PATH,
    SHOW_INDEX_PATH,
    load_or_create_index,
    save_index,
    upsert_vector,
)
from app.models.band import Band
from app.models.show import Show

_DIM = 768  # nomic-embed-text


async def embed_and_index_band(db: Session, band: Band) -> None:
    """Generate an embedding for a Band and persist it to the DB and FAISS index."""
    genres = ", ".join(band.genres) if band.genres else ""
    text = f"{band.name}. Genres: {genres}. {band.description or ''}".strip(". ")
    arr = await embed(text)
    band.embedding = arr.tobytes()
    index = load_or_create_index(BAND_INDEX_PATH, _DIM)
    upsert_vector(index, band.id, arr)
    save_index(index, BAND_INDEX_PATH)


async def embed_and_index_show(db: Session, show: Show) -> None:
    """Generate an embedding for a Show and persist it to the DB and FAISS index."""
    headliner = show.acts[0].band.name if show.acts else ""
    genres = ", ".join(show.acts[0].band.genres) if show.acts else ""
    venue_name = show.venue.name if show.venue else ""
    city = show.venue.city if show.venue else ""
    notes = show.notes or ""
    text = f"{headliner} at {venue_name}, {city}. Genres: {genres}. {notes}".strip(". ")
    arr = await embed(text)
    show.embedding = arr.tobytes()
    index = load_or_create_index(SHOW_INDEX_PATH, _DIM)
    upsert_vector(index, show.id, arr)
    save_index(index, SHOW_INDEX_PATH)
