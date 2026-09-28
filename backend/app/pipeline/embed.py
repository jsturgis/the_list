"""Embedding generation and FAISS indexing helpers."""
from __future__ import annotations

import asyncio
from typing import Optional

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
_loop = asyncio.get_event_loop


def _run_sync(fn, *args):
    """Run a blocking function in the default thread pool."""
    return asyncio.get_event_loop().run_in_executor(None, fn, *args)


async def embed_and_index_band(db: Session, band: Band) -> None:
    """Generate an embedding for a Band and persist it to the DB and FAISS index."""
    genres = ", ".join(band.genres) if band.genres else ""
    text = f"{band.name}. Genres: {genres}. {band.description or ''}".strip(". ")
    arr = await embed(text)
    band.embedding = arr.tobytes()
    index = await _run_sync(load_or_create_index, BAND_INDEX_PATH, _DIM)
    await _run_sync(upsert_vector, index, band.id, arr)
    await _run_sync(save_index, index, BAND_INDEX_PATH)


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
    index = await _run_sync(load_or_create_index, SHOW_INDEX_PATH, _DIM)
    await _run_sync(upsert_vector, index, show.id, arr)
    await _run_sync(save_index, index, SHOW_INDEX_PATH)


async def batch_embed_and_index(
    db: Session,
    shows: list[Show],
) -> None:
    """Embed all shows and their headliner bands, updating each FAISS index once."""
    band_index = await _run_sync(load_or_create_index, BAND_INDEX_PATH, _DIM)
    show_index = await _run_sync(load_or_create_index, SHOW_INDEX_PATH, _DIM)

    seen_band_ids: set[int] = set()

    for show in shows:
        headliner = show.acts[0].band.name if show.acts else ""
        genres = ", ".join(show.acts[0].band.genres) if show.acts else ""
        venue_name = show.venue.name if show.venue else ""
        city = show.venue.city if show.venue else ""
        notes = show.notes or ""
        show_text = f"{headliner} at {venue_name}, {city}. Genres: {genres}. {notes}".strip(". ")
        show_arr = await embed(show_text)
        show.embedding = show_arr.tobytes()
        await _run_sync(upsert_vector, show_index, show.id, show_arr)

        if show.acts:
            band = show.acts[0].band
            if band.id not in seen_band_ids:
                seen_band_ids.add(band.id)
                band_genres = ", ".join(band.genres) if band.genres else ""
                band_text = f"{band.name}. Genres: {band_genres}. {band.description or ''}".strip(". ")
                band_arr = await embed(band_text)
                band.embedding = band_arr.tobytes()
                await _run_sync(upsert_vector, band_index, band.id, band_arr)

    await _run_sync(save_index, band_index, BAND_INDEX_PATH)
    await _run_sync(save_index, show_index, SHOW_INDEX_PATH)
