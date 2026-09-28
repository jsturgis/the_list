from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.show import AgeRestriction, ShowStatus
from app.schemas.show import ShowRead

router = APIRouter()


@router.get("/", response_model=list[ShowRead])
def list_shows(
    db: Session = Depends(get_db),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    city: str | None = Query(None),
    region: str | None = Query(None),
    band_name: str | None = Query(None),
    price_max: float | None = Query(None),
    is_free: bool | None = Query(None),
    age_restriction: AgeRestriction | None = Query(None),
    is_recommended: bool | None = Query(None),
    status: ShowStatus = Query(ShowStatus.upcoming),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    # TODO: implement filtered query
    raise NotImplementedError


@router.get("/{show_id}", response_model=ShowRead)
def get_show(show_id: int, db: Session = Depends(get_db)):
    # TODO: implement
    raise NotImplementedError
