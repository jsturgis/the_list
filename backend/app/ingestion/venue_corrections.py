"""Venues whose calendar page auto-discovery (app/ingestion/venue_calendar.py) gets wrong, or that have none worth
scraping (a third-party embed, a login wall, nothing but a social feed), put right by hand.

A correction's `calendar_url`, when set, is used directly and discovery is never run for that Venue; it's read
like any found calendar. It can be a ticket seller's page for the Venue when that's where its listings are: links
on the same site as the calendar count as the Venue's own. Left as None, it marks the Venue as deliberately not
attempted at all -- discovery is skipped and no calendar_url is set, exactly as if nothing had been found.

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
    # /calendar loads its listings with JavaScript; the homepage lists them in its HTML.
    "the-independent": VenueCorrection(calendar_url="https://www.theindependentsf.com/"),
    # /events carries only past events; its upcoming ones are on its Prekindle page.
    "the-cornerstone": VenueCorrection(calendar_url="https://www.prekindle.com/events/cornerstone"),
    # Its own site refuses automated requests (403); it sells through this Eventim storefront.
    "rickshaw-stop": VenueCorrection(calendar_url="https://wl.eventim.us/RickshawStop"),
}


def venue_correction(name: str) -> VenueCorrection | None:
    """The correction for the Venue with this name, or None."""
    return CORRECTIONS.get(slugify(name))
