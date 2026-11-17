"""Check that what Google Places found for a new Venue is the Venue the List names.

Places answers a text search ("the Giants Ballpark San Francisco") with its best guesses, and something always
comes back: a neighbourhood for "the Castro", a bare street address for a studio it doesn't know, an unrelated
church for "First Church of the Buzzard", twenty houses for "a house". Its details (address, coordinates, place id)
are only worth storing when the place is the Venue: a wrong place id is worse than none, as a listing joins the
Venue at the same Google place (app/ingestion/upsert.find_venue).

A result is **confirmed** when it's a place people go to (not an area or an address), in the listing's city, and
its name is the listed one: the same words, give or take what Steve leaves out or misspells ("the Arena" is Oakland
Arena, "Temescal Arts Center" is Temescal Art Center, "Alameda County Fair" is Alameda County Fairgrounds). A
result that is only the listing's street address is **address only**: where the Venue is, but not a place of its
own. Anything else is **unconfirmed**: the Venue is stored as Steve lists it, without Google's details, and the
ingest says so in its log. A nickname Google can't tie to its place ("the Giants Ballpark" for Oracle Park) ends
up there too: give it the Venue's name in `_VENUE_ALIASES` (app/ingestion/upsert.py).
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from app.ingestion.upsert import _name_key

CONFIRMED, ADDRESS_ONLY, UNCONFIRMED, NOT_FOUND, NOT_CHECKED = (
    "confirmed", "address_only", "unconfirmed", "not_found", "not_checked")

# What a place that isn't a Venue is to Google: an area, a road or an address.
_AREA_TYPES = {"neighborhood", "political", "locality", "sublocality", "sublocality_level_1", "postal_code",
               "administrative_area_level_1", "administrative_area_level_2", "administrative_area_level_3",
               "country", "route", "intersection"}
_ADDRESS_TYPES = {"premise", "subpremise", "street_address"}
_PLACE_TYPES = {"establishment", "point_of_interest"}
# Words that don't tell one Venue from another.
_FILLER = {"the", "a", "an", "of", "at", "and", "in", "on"}
# How alike two words must be to be one misspelt ("arts"/"art" are caught as a prefix), and the shortest prefix
# that counts ("fair"/"fairgrounds").
_WORD_SIMILARITY = 0.8
_PREFIX_LENGTH = 3
_FIELDS_OF_AN_ADDRESS = ("address", "city", "latitude", "longitude", "timezone")


@dataclass(frozen=True)
class VenueCheck:
    status: str
    reason: str = ""            # for the log, when not confirmed
    google_name: str | None = None

    @property
    def details(self) -> tuple[str, ...] | None:
        """Which of the result's fields to keep: all (None) when confirmed, the address's when it's only that."""
        return None if self.status in (CONFIRMED, NOT_CHECKED) else _FIELDS_OF_AN_ADDRESS


def _words(name: str) -> list[str]:
    words = re.sub(r"[^\w\s]", " ", _name_key(name)).split()
    return [w for w in words if w not in _FILLER] or words


def _same_word(a: str, b: str) -> bool:
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= _PREFIX_LENGTH and longer.startswith(shorter):
        return True
    return len(shorter) > _PREFIX_LENGTH and difflib.SequenceMatcher(None, a, b).ratio() >= _WORD_SIMILARITY


def _within(words: list[str], others: list[str]) -> bool:
    """Whether every one of `words` is among `others`."""
    return bool(words) and all(any(_same_word(w, o) for o in others) for w in words)


def same_name(listed: str, google: str) -> bool:
    """Whether Google's name for a place is the listed Venue's: every word of one is in the other, so a shorter or
    longer form of the same name, with words allowed a typo."""
    ours, theirs = _words(listed), _words(google)
    return _within(ours, theirs) or _within(theirs, ours)


def _same_city(city: str | None, found: dict) -> bool:
    """Whether the place is in the listing's city: Google's city is it, or its address names it (Google files Rio
    Nido's roadhouse under Guerneville, with "Rio Nido" in the address). A nearby city doesn't count, even in the
    same Region: "Hopmonk" in Petaluma isn't the HopMonk Tavern in Novato."""
    if not city:
        return True
    place_city, address = found.get("city") or "", found.get("address") or ""
    # The city as a part of the address of its own ("..., Rio Nido, CA 95471"), not a street named after it.
    address_parts = {part.strip().lower() for part in address.split(",")}
    return place_city.lower() == city.lower() or city.lower() in address_parts


def _street_number(text: str | None) -> str | None:
    m = re.match(r"\s*(\d+)", text or "")
    return m.group(1) if m else None


def check_venue(name: str, city: str | None, street: str | None, found: dict) -> VenueCheck:
    """How far Google's result `found` (pipeline.enrichment._enrich_venue) can be trusted for the listed Venue."""
    if not found:
        return VenueCheck(NOT_FOUND, "Google Places has no such place")
    if "google_name" not in found:
        return VenueCheck(NOT_CHECKED)   # a result from before names were asked for
    google_name, types = found.get("google_name") or "", set(found.get("google_types") or [])
    described = f"{google_name!r} ({found.get('address')})"
    if not _same_city(city, found):
        return VenueCheck(UNCONFIRMED, f"Google's best match, {described}, isn't in {city}", google_name)
    if types & _ADDRESS_TYPES and not types & _PLACE_TYPES:
        number = _street_number(street)
        if number and number == _street_number(found.get("address")):
            return VenueCheck(ADDRESS_ONLY, f"Google knows the address, {described}, but no place there", google_name)
        return VenueCheck(UNCONFIRMED, f"Google's best match is an address, {described}", google_name)
    if types & _AREA_TYPES and not types & _PLACE_TYPES:
        return VenueCheck(UNCONFIRMED, f"Google's best match is an area, {described}", google_name)
    # Several results are guesses at a name Google doesn't know ("a house"): only its very name will do.
    if found.get("google_results", 1) > 1:
        if _name_key(google_name) == _name_key(name):
            return VenueCheck(CONFIRMED, google_name=google_name)
        return VenueCheck(UNCONFIRMED, f"Google has {found['google_results']} guesses, the first {described}", google_name)
    if same_name(name, google_name):
        return VenueCheck(CONFIRMED, google_name=google_name)
    return VenueCheck(UNCONFIRMED, f"Google's best match is {described}", google_name)


def checked_details(found: dict, check: VenueCheck) -> dict:
    """The part of Google's result to store for the Venue, given its check: all of it, its address, or nothing."""
    if check.status in (CONFIRMED, NOT_CHECKED):
        return found
    if check.status == ADDRESS_ONLY:
        return {key: found.get(key) for key in _FIELDS_OF_AN_ADDRESS}
    return {}
