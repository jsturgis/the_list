"""Parse raw Steve List plain-text email body into RawShow records."""
from dataclasses import dataclass, field
from datetime import date, time


@dataclass
class RawShow:
    raw_text: str
    date: date | None = None
    bands: list[str] = field(default_factory=list)
    venue_name: str | None = None
    city: str | None = None
    age_restriction: str | None = None
    price_raw: str | None = None
    door_time: str | None = None
    set_time: str | None = None
    is_recommended: bool = False    # *
    will_sell_out: bool = False     # $
    is_pit: bool = False            # @
    is_drink_tickets: bool = False  # ^
    is_no_reentry: bool = False     # #
    status: str = "upcoming"        # upcoming | cancelled | postponed
    notes: str | None = None


def parse_email_body(plain_text: str) -> list[RawShow]:
    """Parse decoded email plain text into a list of RawShow records.

    The email format is loosely structured plain text — an LLM extraction
    pass (see pipeline/enrichment.py) handles the final structuring.
    This function does a first-pass split into per-show text blocks.
    """
    # TODO: split on date lines, group continuation lines, extract flags
    raise NotImplementedError
