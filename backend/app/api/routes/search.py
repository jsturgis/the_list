from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.band import BandRead
from app.schemas.show import ShowRead

router = APIRouter()


@router.get("/bands", response_model=list[BandRead])
def fuzzy_band_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    # TODO: trigram / fuzzy match on Band.name
    raise NotImplementedError


@router.get("/shows/similar/{show_id}", response_model=list[ShowRead])
def similar_shows(
    show_id: int,
    k: int = Query(10, le=50),
    db: Session = Depends(get_db),
):
    # TODO: look up show embedding → FAISS search → return Show records
    raise NotImplementedError
