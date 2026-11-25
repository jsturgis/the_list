"""Shows Steve lists on the wrong day, put right by hand.

A listing whose date and weekday agree but are wrong can't be told from the page itself (a misspelt month can:
app/ingestion/parser.py). The Venue's own calendar says the day; a correction moves the listing to it before it's
stored, so it's the Show at the Venue that day: one already added from the Venue's event page (an ingest job) is
that Show and becomes the List's, and the Show stored on the wrong day is no longer listed and is removed
(app/ingestion/upsert.py remove_unlisted_shows).

A correction is keyed by the listing as Steve has it: its date, its Venue (app/ingestion/upsert.venue_key, so a
Venue's other names count) and its headliner (app/ingestion/upsert.band_key, its slug). Once Steve puts the date
right himself, nothing is listed under the key and the correction does nothing; it can go once that day has passed.
"""
from __future__ import annotations

from datetime import date

from app.ingestion.upsert import band_key, venue_key

# (the date Steve lists, the Venue, the headliner) -> the day the Show is on
CORRECTIONS: dict[tuple[date, str, str], date] = {
    # "nov 30 mon Time Spent /Driving, The New Trust, Midcourse Correction at Kilowatt": Kilowatt's calendar (its
    # DICE listings, https://kilowattbar.com/events) has Time Spent Driving and The New Trust on Sunday Nov 29, 7pm.
    (date(2026, 11, 30), venue_key("Kilowatt"), band_key("Time Spent Driving")): date(2026, 11, 29),
}


def corrected_date(listed: date, venue_name: str, city: str | None, headliner: str | None) -> date:
    """The day a listing's Show is on: its correction's, else the date Steve lists."""
    if not headliner:
        return listed
    return CORRECTIONS.get((listed, venue_key(venue_name, city), band_key(headliner)), listed)
