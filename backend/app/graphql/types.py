from __future__ import annotations
import strawberry
from datetime import date, datetime, time


@strawberry.type
class VenueType:
    id: int
    name: str
    address: str | None
    city: str
    region: str
    website_url: str | None
    latitude: float | None
    longitude: float | None
    timezone: str | None
    phone: str | None
    google_rating: float | None
    google_place_id: str | None
    description: str | None
    wikipedia_url: str | None
    neighborhood: str | None
    venue_type: str | None
    nearest_transit: str | None
    instagram: str | None
    image_url: str | None
    default_age_restriction: str | None
    is_sober_space: bool | None
    is_cash_only: bool | None
    membership_required: bool | None


@strawberry.type
class BandType:
    id: int
    name: str
    genres: list[str]
    spotify_url: str | None
    soundcloud_url: str | None
    bandcamp_url: str | None
    website_url: str | None
    image_url: str | None
    is_local: bool | None


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
    notes: str | None
    is_matinee: bool
    is_sold_out: bool
    ticket_provider: str | None
    is_benefit: bool
    benefit_cause: str | None
    special_event: str | None


@strawberry.type
class FilterOptionsType:
    regions: list[str]
    ages: list[str]
    genres: list[str]
    dates: list[str]


@strawberry.type
class IngestionRunType:
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    email_received_at: datetime | None
    email_subject: str | None
    email_message_id: str | None
    shows_parsed: int | None
    shows_upserted: int | None
    shows_new: int | None
    error: str | None


@strawberry.input
class ShowFilters:
    from_date: date | None = None
    to_date: date | None = None
    city: str | None = None
    region: str | None = None
    venue_id: int | None = None
    band_id: int | None = None
    band_name: str | None = None
    venue_name: str | None = None
    genre: str | None = None
    price_max: float | None = None
    is_free: bool | None = None
    age_restriction: str | None = None
    is_recommended: bool | None = None
    status: str = "upcoming"
