"""Embedding generation and FAISS indexing helpers.

Embedding a text takes Ollama a fraction of a second, and replacing a vector in a flat FAISS index scans it, so the
ingest embeds only what changed: the digest of each record's text when it was last embedded is kept beside the
indexes (texts.json), and a Show or Band whose text has the same digest, and that has an embedding, is skipped.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.config import settings
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

logger = logging.getLogger(__name__)

_DIM = 768  # nomic-embed-text
TEXTS_PATH = os.path.join(settings.faiss_index_path, "texts.json")


def _run_sync(fn, *args):
    """Run a blocking function in the default thread pool."""
    return asyncio.get_event_loop().run_in_executor(None, fn, *args)


def _show_text(show: Show) -> str:
    headliner = show.acts[0].band.name if show.acts else ""
    genres = ", ".join(show.acts[0].band.genres) if show.acts else ""
    venue_name = show.venue.name if show.venue else ""
    city = show.venue.city if show.venue else ""
    notes = show.notes or ""
    return f"{headliner} at {venue_name}, {city}. Genres: {genres}. {notes}".strip(". ")


def _band_text(band: Band) -> str:
    genres = ", ".join(band.genres) if band.genres else ""
    return f"{band.name}. Genres: {genres}".strip(". ")


def _digest(text: str) -> str:
    """The text's digest, with the embedding model's name: a new model embeds everything again."""
    return hashlib.sha256(f"{settings.ollama_embedding_model}\n{text}".encode()).hexdigest()[:16]


def load_texts(path: Optional[str] = None) -> dict[str, dict[str, str]]:
    """Each record's text digest when it was last embedded, by kind ("shows", "bands") and id; empty when there's
    no file or it can't be read (everything is then embedded again)."""
    try:
        with open(path or TEXTS_PATH) as f:
            data = json.load(f)
        return {"shows": dict(data.get("shows") or {}), "bands": dict(data.get("bands") or {})}
    except (OSError, ValueError, AttributeError):
        return {"shows": {}, "bands": {}}


def save_texts(texts: dict[str, dict[str, str]], path: Optional[str] = None) -> None:
    path = path or TEXTS_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(texts, f, sort_keys=True, separators=(",", ":"))


def _unchanged(texts: dict[str, str], record_id: int, embedding: Optional[bytes], text: str) -> bool:
    return embedding is not None and texts.get(str(record_id)) == _digest(text)


async def embed_and_index_band(db: Session, band: Band) -> None:
    """Generate an embedding for a Band and persist it to the DB and FAISS index."""
    text = _band_text(band)
    arr = await embed(text)
    band.embedding = arr.tobytes()
    index = await _run_sync(load_or_create_index, BAND_INDEX_PATH, _DIM)
    await _run_sync(upsert_vector, index, band.id, arr)
    await _run_sync(save_index, index, BAND_INDEX_PATH)
    texts = load_texts()
    texts["bands"][str(band.id)] = _digest(text)
    save_texts(texts)


async def embed_and_index_show(db: Session, show: Show) -> None:
    """Generate an embedding for a Show and persist it to the DB and FAISS index."""
    text = _show_text(show)
    arr = await embed(text)
    show.embedding = arr.tobytes()
    index = await _run_sync(load_or_create_index, SHOW_INDEX_PATH, _DIM)
    await _run_sync(upsert_vector, index, show.id, arr)
    await _run_sync(save_index, index, SHOW_INDEX_PATH)
    texts = load_texts()
    texts["shows"][str(show.id)] = _digest(text)
    save_texts(texts)


async def batch_embed_and_index(
    db: Session,
    shows: list[Show],
) -> None:
    """Embed the shows and their headliner bands whose text changed (see the module docstring), updating each FAISS
    index once."""
    texts = load_texts()
    band_index = show_index = None
    embedded_shows = embedded_bands = 0
    seen_band_ids: set[int] = set()

    for show in shows:
        show_text = _show_text(show)
        if not _unchanged(texts["shows"], show.id, show.embedding, show_text):
            show_index = show_index or await _run_sync(load_or_create_index, SHOW_INDEX_PATH, _DIM)
            show_arr = await embed(show_text)
            show.embedding = show_arr.tobytes()
            await _run_sync(upsert_vector, show_index, show.id, show_arr)
            texts["shows"][str(show.id)] = _digest(show_text)
            embedded_shows += 1

        if show.acts:
            band = show.acts[0].band
            if band.id not in seen_band_ids:
                seen_band_ids.add(band.id)
                band_text = _band_text(band)
                if not _unchanged(texts["bands"], band.id, band.embedding, band_text):
                    band_index = band_index or await _run_sync(load_or_create_index, BAND_INDEX_PATH, _DIM)
                    band_arr = await embed(band_text)
                    band.embedding = band_arr.tobytes()
                    await _run_sync(upsert_vector, band_index, band.id, band_arr)
                    texts["bands"][str(band.id)] = _digest(band_text)
                    embedded_bands += 1

    if band_index is not None:
        await _run_sync(save_index, band_index, BAND_INDEX_PATH)
    if show_index is not None:
        await _run_sync(save_index, show_index, SHOW_INDEX_PATH)
    # After the indexes: a digest is only ever saved for a vector that's in its index.
    if band_index is not None or show_index is not None:
        save_texts(texts)
    logger.info("embedding: %d of %d shows and %d bands changed and were embedded", embedded_shows, len(shows),
                embedded_bands)
