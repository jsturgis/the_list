"""Similarity search against Band and Show FAISS indices."""
import numpy as np

from app.embeddings.indexer import (
    BAND_INDEX_PATH,
    SHOW_INDEX_PATH,
    load_or_create_index,
)

_EMBEDDING_DIM = 768  # nomic-embed-text; update if switching models


def find_similar_bands(embedding: np.ndarray, k: int = 10) -> list[tuple[int, float]]:
    """Return (band_id, distance) for the k most similar Bands."""
    index = load_or_create_index(BAND_INDEX_PATH, _EMBEDDING_DIM)
    distances, ids = index.search(embedding.reshape(1, -1), k)
    return [(int(i), float(d)) for i, d in zip(ids[0], distances[0]) if i != -1]


def find_similar_shows(embedding: np.ndarray, k: int = 10) -> list[tuple[int, float]]:
    """Return (show_id, distance) for the k most similar Shows."""
    index = load_or_create_index(SHOW_INDEX_PATH, _EMBEDDING_DIM)
    distances, ids = index.search(embedding.reshape(1, -1), k)
    return [(int(i), float(d)) for i, d in zip(ids[0], distances[0]) if i != -1]
