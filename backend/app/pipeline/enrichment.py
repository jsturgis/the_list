"""Enrichment chain: MusicBrainz genres/URLs, Google Maps venue data, ticket URL."""
from __future__ import annotations

import re
import time as _time
from functools import lru_cache
from typing import Optional

import httpx
import musicbrainzngs
from pydantic import BaseModel

from app.config import settings
from app.ingestion.parser import RawShow
from app.pipeline.providers import get_enrichment_llm

musicbrainzngs.set_useragent(
    settings.musicbrainz_app_name,
    settings.musicbrainz_app_version,
    settings.musicbrainz_contact,
)
musicbrainzngs.set_rate_limit(True)

_MB_SCORE_THRESHOLD = 90
_PLACES_FIELD_MASK = "places.formattedAddress,places.location,places.websiteUri,places.id,places.nationalPhoneNumber,places.rating,places.utcOffsetMinutes"
_TICKET_RE = re.compile(
    r'https?://(?:www\.)?(?:eventbrite|ticketmaster|axs|dice|seated|bandsintown)\.[a-z]{2,3}/[^\s"\'<>]+',
    re.IGNORECASE,
)


class _GenreList(BaseModel):
    genres: list[str]


# ── MusicBrainz ───────────────────────────────────────────────────────────────

def _mb_search(name: str) -> Optional[dict]:
    """Return the best-match MB artist dict (score >= threshold), or None."""
    try:
        result = musicbrainzngs.search_artists(artist=name, limit=5)
    except Exception:
        return None
    for artist in result.get("artist-list", []):
        if int(artist.get("ext:score", "0")) >= _MB_SCORE_THRESHOLD:
            return artist
    return None


def _mb_lookup(mbid: str) -> dict:
    """Return the full MB artist record with tags and URL rels."""
    try:
        return musicbrainzngs.get_artist_by_id(mbid, includes=["tags", "url-rels"])["artist"]
    except Exception:
        return {}


def _extract_genres_via_llm(text: str) -> list[str]:
    llm = get_enrichment_llm()
    chain = llm.with_structured_output(_GenreList)
    result = chain.invoke(
        "Extract 1–5 concise music genre tags from the text below. "
        "Reply with a list of short lowercase strings like 'punk' or 'indie rock'.\n\n"
        + text
    )
    return result.genres


def _scrape_text(url: str) -> Optional[str]:
    """Fetch a URL and return stripped text (first 3000 chars), or None on error."""
    try:
        resp = httpx.get(
            url, timeout=10.0, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        text = re.sub(r"<[^>]+>", " ", resp.text)
        return text[:3000]
    except Exception:
        return None


def _find_soundcloud_url(name: str) -> Optional[str]:
    """Ask LLM for the likely SoundCloud slug, then verify it exists."""
    llm = get_enrichment_llm()
    try:
        result = llm.invoke(
            f"What is the SoundCloud URL slug for the musical artist '{name}'? "
            "Reply with ONLY the slug (e.g. 'the-national'), nothing else. "
            "If you are not confident, reply with 'unknown'."
        )
        slug = result.content.strip().lower().strip("/")
        if not slug or slug == "unknown" or " " in slug:
            return None
        url = f"https://soundcloud.com/{slug}"
        resp = httpx.head(url, timeout=5.0, follow_redirects=True)
        return url if resp.status_code == 200 else None
    except Exception:
        return None


def _generate_description(name: str, disambiguation: Optional[str], genres: list[str], tags: list[str]) -> Optional[str]:
    """Generate a one-sentence band description using known facts. No speculation."""
    if not genres and not disambiguation:
        return disambiguation
    parts = []
    if disambiguation:
        parts.append(f"Known as: {disambiguation}")
    if genres:
        parts.append(f"Genres: {', '.join(genres)}")
    if tags and len(tags) > len(genres):
        extra = [t for t in tags if t not in genres][:5]
        if extra:
            parts.append(f"Also tagged: {', '.join(extra)}")
    llm = get_enrichment_llm()
    try:
        result = llm.invoke(
            f"Write one concise sentence describing the musical artist '{name}' "
            f"using only these known facts:\n" + "\n".join(parts) +
            "\nReturn only the sentence. Do not speculate or add unknown details."
        )
        return result.content.strip()
    except Exception:
        return disambiguation


def _enrich_band(name: str) -> dict:
    """Return {genres, spotify_url, soundcloud_url, description} for a band name."""
    artist = _mb_search(name)
    if artist is None:
        return {"genres": [], "spotify_url": None, "soundcloud_url": None, "description": None}

    full = _mb_lookup(artist["id"])
    disambiguation = full.get("disambiguation")

    tags = sorted(
        full.get("tag-list", []),
        key=lambda t: int(t.get("count", 0)),
        reverse=True,
    )
    genres = [t["name"] for t in tags[:5]]
    all_tag_names = [t["name"] for t in tags]

    spotify_url: Optional[str] = None
    soundcloud_url: Optional[str] = None
    for rel in full.get("url-relation-list", []):
        target = rel.get("target", "")
        rel_type = rel.get("type", "")
        if not spotify_url and "spotify.com" in target and rel_type == "streaming music":
            spotify_url = target
        if not soundcloud_url and "soundcloud.com" in target:
            soundcloud_url = target

    # LLM fallback: find SoundCloud URL when MB doesn't have one
    if not soundcloud_url:
        soundcloud_url = _find_soundcloud_url(name)

    # LLM fallback: genres empty + SoundCloud page available to scrape
    if not genres and soundcloud_url:
        scraped = _scrape_text(soundcloud_url)
        if scraped:
            genres = _extract_genres_via_llm(scraped)

    description = _generate_description(name, disambiguation, genres, all_tag_names)

    return {
        "genres": genres,
        "spotify_url": spotify_url,
        "soundcloud_url": soundcloud_url,
        "description": description,
    }


# ── Google Maps ───────────────────────────────────────────────────────────────

def _get_timezone(lat: float, lng: float, api_key: str) -> Optional[str]:
    """Return IANA timezone ID for a lat/lng pair using the Google Timezone API."""
    try:
        resp = httpx.get(
            "https://maps.googleapis.com/maps/api/timezone/json",
            params={"location": f"{lat},{lng}", "timestamp": int(_time.time()), "key": api_key},
            timeout=10.0,
        )
        data = resp.json()
        if data.get("status") == "OK":
            return data.get("timeZoneId")
    except Exception:
        pass
    return None


@lru_cache(maxsize=512)
def _enrich_venue(venue_name: str, city: str) -> dict:
    """Return venue enrichment dict from Google Places + Timezone APIs, or {}."""
    api_key = settings.google_maps_api_key
    if not api_key:
        return {}
    try:
        resp = httpx.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _PLACES_FIELD_MASK},
            json={"textQuery": f"{venue_name} {city}"},
            timeout=10.0,
        )
        data = resp.json()
    except Exception:
        return {}

    places = data.get("places", [])
    if not places:
        return {}

    place = places[0]
    loc = place.get("location", {})
    lat = loc.get("latitude")
    lng = loc.get("longitude")
    timezone = _get_timezone(lat, lng, api_key) if lat and lng else None

    return {
        "address": place.get("formattedAddress"),
        "website_url": place.get("websiteUri"),
        "latitude": lat,
        "longitude": lng,
        "google_place_id": place.get("id"),
        "phone": place.get("nationalPhoneNumber"),
        "google_rating": place.get("rating"),
        "timezone": timezone,
    }


# ── Ticket URL ────────────────────────────────────────────────────────────────

def _find_ticket_url(venue_website: Optional[str], headliner: str) -> Optional[str]:
    """Try venue site → Eventbrite → Ticketmaster. Return first ticket URL found."""
    q = headliner.replace(" ", "+")
    sources = [
        f"https://www.eventbrite.com/d/ca--san-francisco/concerts/?q={q}",
        f"https://www.ticketmaster.com/search?q={q}&type=event",
    ]
    if venue_website:
        sources.insert(0, venue_website)

    for url in sources:
        try:
            resp = httpx.get(url, timeout=5.0, follow_redirects=True)
            if resp.status_code == 200:
                m = _TICKET_RE.search(resp.text)
                if m:
                    return m.group(0)
        except Exception:
            pass
    return None


# ── Main entry point ──────────────────────────────────────────────────────────

async def enrich_show(raw: RawShow) -> dict:
    """Enrich a RawShow. Returns a dict ready for upsert_shows()."""
    result: dict = {
        "date": raw.date,
        "bands": raw.bands,
        "venue_name": raw.venue_name,
        "city": raw.city,
        "door_time": raw.door_time,
        "set_time": raw.set_time,
        "price_raw": raw.price_raw,
        "age_restriction": raw.age_restriction,
        "status": raw.status,
        "is_recommended": raw.is_recommended,
        "will_sell_out": raw.will_sell_out,
        "is_pit": raw.is_pit,
        "is_drink_tickets": raw.is_drink_tickets,
        "is_no_reentry": raw.is_no_reentry,
        "notes": raw.notes,
        "raw_text": raw.raw_text,
        "genres": [],
        "spotify_url": None,
        "soundcloud_url": None,
        "description": None,
        "venue_website": None,
        "address": None,
        "latitude": None,
        "longitude": None,
        "google_place_id": None,
        "phone": None,
        "google_rating": None,
        "timezone": None,
        "ticket_url": None,
    }

    headliner = raw.bands[0] if raw.bands else None
    if headliner:
        band_data = _enrich_band(headliner)
        result["genres"] = band_data["genres"]
        result["spotify_url"] = band_data["spotify_url"]
        result["soundcloud_url"] = band_data["soundcloud_url"]
        result["description"] = band_data["description"]

    if raw.venue_name:
        venue_data = _enrich_venue(raw.venue_name, raw.city or "")
        result["address"] = venue_data.get("address")
        result["venue_website"] = venue_data.get("website_url")
        result["latitude"] = venue_data.get("latitude")
        result["longitude"] = venue_data.get("longitude")
        result["google_place_id"] = venue_data.get("google_place_id")
        result["phone"] = venue_data.get("phone")
        result["google_rating"] = venue_data.get("google_rating")
        result["timezone"] = venue_data.get("timezone")

    is_free = (raw.price_raw or "").strip().lower() == "free"
    if not is_free and headliner:
        result["ticket_url"] = _find_ticket_url(result["venue_website"], headliner)

    return result
