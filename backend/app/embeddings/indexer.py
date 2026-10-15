"""Build and persist FAISS indices for Band and Show embeddings."""
import os

import faiss
import numpy as np

from app.config import settings

BAND_INDEX_PATH = os.path.join(settings.faiss_index_path, "bands.index")
SHOW_INDEX_PATH = os.path.join(settings.faiss_index_path, "shows.index")


def load_or_create_index(path: str, dim: int) -> faiss.Index:
    if os.path.exists(path):
        return faiss.read_index(path)
    return faiss.IndexIDMap(faiss.IndexFlatL2(dim))


def save_index(index: faiss.Index, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    faiss.write_index(index, path)


def upsert_vector(index: faiss.Index, record_id: int, vector: np.ndarray) -> None:
    """Remove existing vector for record_id (if any) and add the new one."""
    try:
        index.remove_ids(np.array([record_id], dtype=np.int64))
    except Exception:
        pass
    index.add_with_ids(
        vector.reshape(1, -1),
        np.array([record_id], dtype=np.int64),
    )


def remove_from_index(path: str, record_ids: list[int]) -> None:
    """Remove these records' vectors from the index saved at `path` (e.g. Bands merged away); nothing if none is."""
    if not os.path.exists(path):
        return
    index = faiss.read_index(path)
    index.remove_ids(np.array(record_ids, dtype=np.int64))
    save_index(index, path)


def add_to_index(path: str, vectors: dict[int, np.ndarray | bytes]) -> None:
    """Add (or replace) these records' vectors in the index saved at `path`, creating it if there's none."""
    if not vectors:
        return
    arrays = {i: np.frombuffer(v, dtype=np.float32) if isinstance(v, bytes) else v for i, v in vectors.items()}
    index = load_or_create_index(path, len(next(iter(arrays.values()))))
    for record_id, vector in arrays.items():
        upsert_vector(index, record_id, vector)
    save_index(index, path)
