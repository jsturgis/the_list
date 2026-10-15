"""Tests for indexing the stored vectors the FAISS indexes are missing."""
from __future__ import annotations

import faiss
import numpy as np

from app.embeddings.indexer import add_to_index, load_or_create_index, save_index
from app.ingestion.index_stored_vectors import index_stored_vectors
from app.models.band import Band


def _vec(x: float) -> np.ndarray:
    return np.full(4, x, dtype=np.float32)


def _ids(path: str) -> list[int]:
    index = load_or_create_index(path, 4)  # held: its id_map is freed with it
    return sorted(faiss.vector_to_array(index.id_map).tolist())


def test_adding_vectors_to_a_saved_index_keeps_the_rest(tmp_path):
    path = str(tmp_path / "bands.index")
    index = load_or_create_index(path, 4)
    index.add_with_ids(_vec(1).reshape(1, -1), np.array([1], dtype=np.int64))
    save_index(index, path)

    add_to_index(path, {2: _vec(2), 3: _vec(3).tobytes()})

    assert _ids(path) == [1, 2, 3]


def test_indexes_the_bands_with_a_stored_vector_the_index_lacks(db, tmp_path):
    path = str(tmp_path / "bands.index")
    indexed = Band(name="Indexed", embedding=_vec(1).tobytes())
    missing = Band(name="B.F.H", embedding=_vec(2).tobytes())
    db.add_all([indexed, missing, Band(name="Never embedded")])
    db.commit()
    add_to_index(path, {indexed.id: _vec(1)})

    assert index_stored_vectors(db, Band, path) == [missing.id]   # a dry run: nothing changes
    assert _ids(path) == [indexed.id]

    assert index_stored_vectors(db, Band, path, apply=True) == [missing.id]
    assert _ids(path) == sorted([indexed.id, missing.id])
    assert index_stored_vectors(db, Band, path) == []
