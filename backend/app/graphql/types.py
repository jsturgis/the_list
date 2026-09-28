from __future__ import annotations
import strawberry
from datetime import date, time


@strawberry.type
class VenueType:
    id: int
    name: str
    address: str | None
    city: str
    region: str
    website_url: str | None


@strawberry.type
class BandType:
    id: int
    name: str
    genres: list[str]
    spotify_url: str | None
    soundcloud_url: str | None
    description: str | None


@strawberry.type
class ActType:
    position: int
    band: BandType


@strawberry.type
class ShowType:
    id: int
    date: date
    door_time: time | None
    set_time: time | None
    venue: VenueType
    acts: list[ActType]
    price_min: float | None
    price_max: float | None
    is_free: bool
    age_restriction: str
    status: str
    is_recommended: bool
    will_sell_out: bool
    is_pit: bool
    is_drink_tickets: bool
    is_no_reentry: bool
    ticket_url: str | None
    notes: str | None


@strawberry.input
class ShowFilters:
    from_date: date | None = None
    to_date: date | None = None
    city: str | None = None
    region: str | None = None
    band_name: str | None = None
    price_max: float | None = None
    is_free: bool | None = None
    age_restriction: str | None = None
    is_recommended: bool | None = None
    status: str = "upcoming"
