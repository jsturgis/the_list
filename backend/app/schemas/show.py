from __future__ import annotations
from datetime import date, time

from pydantic import BaseModel

from app.models.show import AgeRestriction, ShowStatus
from app.schemas.band import BandRead
from app.schemas.venue import VenueRead


class ActRead(BaseModel):
    position: int
    band: BandRead

    model_config = {"from_attributes": True}


class ShowRead(BaseModel):
    id: int
    date: date
    door_time: time | None = None
    set_time: time | None = None
    venue: VenueRead
    acts: list[ActRead] = []
    price_min: float | None = None
    price_max: float | None = None
    is_free: bool = False
    age_restriction: AgeRestriction = AgeRestriction.unknown
    status: ShowStatus = ShowStatus.upcoming
    is_recommended: bool = False
    will_sell_out: bool = False
    is_pit: bool = False
    is_drink_tickets: bool = False
    is_no_reentry: bool = False
    ticket_url: str | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}
