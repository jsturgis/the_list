"""Venues whose calendar page auto-discovery (app/ingestion/venue_calendar.py) gets wrong, or that have none worth
scraping (a third-party embed, a login wall, nothing but a social feed), put right by hand.

A correction's `calendar_url`, when set, is used directly and discovery is never run for that Venue. Left as None,
it marks the Venue as deliberately not attempted at all -- discovery is skipped and no calendar_url is set, exactly
as if nothing had been found. Either way, app/ingestion/venue_calendar.py still records calendar_checked_at, so a
corrected Venue is asked at most once unless the correction changes or a recheck is forced (`python -m app.cli
backfill --recheck-calendars`).

Corrections are keyed by the Venue's Slug (app/slugs.py), so the same Venue spelled another way ("The Fillmore",
"Fillmore") finds its own.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.slugs import slugify


@dataclass(frozen=True)
class VenueCorrection:
    calendar_url: str | None = None  # None: deliberately not attempted, not "not found yet"


CORRECTIONS: dict[str, VenueCorrection] = {
    # Add entries as auto-discovery gets a Venue's calendar wrong, or finds the wrong page, e.g.:
    # "some-venue": VenueCorrection(calendar_url="https://example.com/shows/"),
}


def venue_correction(name: str) -> VenueCorrection | None:
    """The correction for the Venue with this name, or None."""
    return CORRECTIONS.get(slugify(name))
