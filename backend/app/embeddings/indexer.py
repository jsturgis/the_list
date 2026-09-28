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
