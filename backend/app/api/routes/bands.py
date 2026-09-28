from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.band import BandRead

router = APIRouter()


@router.get("/", response_model=list[BandRead])
def list_bands(
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Fuzzy band name search"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    # TODO: implement with fuzzy name matching
    raise NotImplementedError


@router.get("/{band_id}", response_model=BandRead)
def get_band(band_id: int, db: Session = Depends(get_db)):
    # TODO: implement
    raise NotImplementedError


@router.get("/{band_id}/similar", response_model=list[BandRead])
def get_similar_bands(
    band_id: int,
    k: int = Query(10, le=50),
    db: Session = Depends(get_db),
):
    # TODO: look up band embedding → FAISS search → return Band records
    raise NotImplementedError
