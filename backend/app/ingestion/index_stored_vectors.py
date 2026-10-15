"""Add to the FAISS indexes the Band and Show vectors stored in the database that they're missing, e.g. a vector a
kept Band took from a duplicate it merged (app.ingestion.dedupe_bands). Without its vector in the index under its
own id, a Band never comes up as anyone's Similar Band.

Dry run by default:   python -m app.ingestion.index_stored_vectors
Index them:           python -m app.ingestion.index_stored_vectors --apply
"""
from __future__ import annotations

import sys

import faiss
from sqlalchemy.orm import Session

from app.embeddings.indexer import add_to_index, load_or_create_index


def index_stored_vectors(db: Session, model, path: str, apply: bool = False) -> list[int]:
    """The ids of `model`'s rows (Band or Show) with a stored vector the index at `path` lacks; added when `apply`."""
    stored = dict(db.query(model.id, model.embedding).filter(model.embedding.isnot(None)).order_by(model.id))
    if not stored:
        return []
    index = load_or_create_index(path, len(stored[next(iter(stored))]) // 4)
    indexed = set(faiss.vector_to_array(index.id_map).tolist())
    missing = {i: v for i, v in stored.items() if i not in indexed}
    if apply:
        add_to_index(path, missing)
    return list(missing)


def main(argv: list[str]) -> None:
    from app.database import SessionLocal
    from app.embeddings.indexer import BAND_INDEX_PATH, SHOW_INDEX_PATH
    from app.models.band import Band
    from app.models.show import Show

    apply = "--apply" in argv
    db = SessionLocal()
    try:
        for model, path in ((Band, BAND_INDEX_PATH), (Show, SHOW_INDEX_PATH)):
            ids = index_stored_vectors(db, model, path, apply=apply)
            names = ""
            if model is Band and ids:
                names = ": " + ", ".join(repr(b.name) for b in db.query(Band).filter(Band.id.in_(ids)).order_by(Band.id))
            print(f"{'Indexed' if apply else 'Would index'} {len(ids)} {model.__tablename__}{names}")
        if not apply:
            print("Dry run: nothing changed. Re-run with --apply to index them.")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
