"""Google Places (the Places API, New): the city a place is in, from Google's parts of its address.

`address_city` reads it from a place Google gave (app/pipeline/enrichment.py's Venue lookup); `city_at` asks Google
for the place nearest some coordinates, for an event that gives only those (app/ingestion/ticketweb.py).
"""
from __future__ import annotations

from functools import lru_cache

import httpx

from app.config import settings
from app.ingestion.service_health import ServiceError

# The parts of an address that name its city. Google gives a few small cities as administrative_area_level_3.
_CITY_TYPES = {"locality", "administrative_area_level_3", "sublocality", "sublocality_level_1"}
# How far from the coordinates the nearest place may be: a Venue's coordinates are on it, or across the street.
_NEARBY_M = 300.0


class PlacesUnavailable(RuntimeError):
    """Google Places couldn't be asked (no key, no answer, an error): where the place is isn't known either way."""


def address_city(place: dict) -> str | None:
    """The city in a Google place's address, if it names one."""
    return next((c.get("longText") for c in place.get("addressComponents", [])
                 if _CITY_TYPES & set(c.get("types", []))), None)


@lru_cache(maxsize=512)
def city_at(latitude: float, longitude: float) -> str | None:
    """The city of the place nearest the coordinates, as Google has it; None when Google knows no place there. Kept
    for the run, as an event's coordinates are read again on its own page and its seller's (an error isn't kept)."""
    if not settings.google_maps_api_key:
        raise PlacesUnavailable("no Google Maps key (GOOGLE_MAPS_API_KEY)")
    try:
        response = httpx.post(
            "https://places.googleapis.com/v1/places:searchNearby",
            headers={"X-Goog-Api-Key": settings.google_maps_api_key, "X-Goog-FieldMask": "places.addressComponents"},
            json={"maxResultCount": 1, "rankPreference": "DISTANCE",
                  "locationRestriction": {"circle": {"center": {"latitude": latitude, "longitude": longitude},
                                                     "radius": _NEARBY_M}}},
            timeout=10.0,
        )
        data = response.json()
        if "error" in data:
            raise ServiceError(f"Places error {response.status_code}: {data['error'].get('message')}")
    except (httpx.HTTPError, ValueError, ServiceError) as exc:
        raise PlacesUnavailable(f"Google Places didn't answer: {exc}") from exc
    places = data.get("places") or []
    return address_city(places[0]) if places else None
