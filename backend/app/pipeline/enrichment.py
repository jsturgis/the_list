"""Enrichment chain: MusicBrainz genres/URLs, Google Maps venue data, ticket URL."""
from __future__ import annotations

import re
import time as _time
from functools import lru_cache
from typing import Optional
from urllib.parse import quote as _url_quote

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

_PLACES_FIELD_MASK = "places.formattedAddress,places.location,places.websiteUri,places.id,places.nationalPhoneNumber,places.rating,places.utcOffsetMinutes"
_WIKI_HEADERS = {"User-Agent": "the-list/1.0 (music discovery app; contact@thelist.app)"}


class _GenreList(BaseModel):
    genres: list[str]


# ── MusicBrainz ───────────────────────────────────────────────────────────────

def _mb_search(name: str) -> Optional[dict]:
    """Return the MB artist whose name exactly matches (case-insensitive), or None."""
    try:
        result = musicbrainzngs.search_artists(artist=f'"{name}"', limit=5)
    except Exception:
        return None
    name_lower = name.lower()
    for artist in result.get("artist-list", []):
        if artist.get("name", "").lower() == name_lower:
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


def _find_bandcamp_url(name: str) -> Optional[str]:
    """Ask LLM for the likely Bandcamp subdomain, then verify it exists."""
    llm = get_enrichment_llm()
    try:
        result = llm.invoke(
            f"What is the Bandcamp subdomain for the musical artist '{name}'? "
            "Reply with ONLY the subdomain (e.g. 'thenational'), nothing else. "
            "If you are not confident, reply with 'unknown'."
        )
        slug = result.content.strip().lower().strip("/")
        if not slug or slug == "unknown" or " " in slug or "." in slug:
            return None
        url = f"https://{slug}.bandcamp.com"
        resp = httpx.head(url, timeout=5.0, follow_redirects=True)
        return url if resp.status_code == 200 else None
    except Exception:
        return None



def _enrich_band(name: str) -> dict:
    """Return {genres, spotify_url, soundcloud_url, bandcamp_url} for a band name."""
    artist = _mb_search(name)
    if artist is None:
        return {"genres": [], "spotify_url": None, "soundcloud_url": None, "bandcamp_url": None}

    full = _mb_lookup(artist["id"])

    tags = sorted(
        full.get("tag-list", []),
        key=lambda t: int(t.get("count", 0)),
        reverse=True,
    )
    genres = [t["name"] for t in tags[:5]]

    spotify_url: Optional[str] = None
    soundcloud_url: Optional[str] = None
    bandcamp_url: Optional[str] = None
    for rel in full.get("url-relation-list", []):
        target = rel.get("target", "")
        rel_type = rel.get("type", "")
        if not spotify_url and "spotify.com" in target and rel_type == "streaming music":
            spotify_url = target
        if not soundcloud_url and "soundcloud.com" in target:
            soundcloud_url = target
        if not bandcamp_url and "bandcamp.com" in target:
            bandcamp_url = target

    # LLM fallback: find SoundCloud URL when MB doesn't have one
    if not soundcloud_url:
        soundcloud_url = _find_soundcloud_url(name)

    # LLM fallback: find Bandcamp URL when both Spotify and SoundCloud are missing
    if not bandcamp_url and not spotify_url and not soundcloud_url:
        bandcamp_url = _find_bandcamp_url(name)

    # LLM fallback: genres empty + SoundCloud page available to scrape
    if not genres and soundcloud_url:
        scraped = _scrape_text(soundcloud_url)
        if scraped:
            genres = _extract_genres_via_llm(scraped)

    return {
        "genres": genres,
        "spotify_url": spotify_url,
        "soundcloud_url": soundcloud_url,
        "bandcamp_url": bandcamp_url,
    }


# ── Wikipedia ────────────────────────────────────────────────────────────────

def _search_wikipedia(name: str, city: str) -> Optional[str]:
    """Return the Wikipedia page title for a venue, or None if not found."""
    query = f"{name} {city}"
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": query,
                    "format": "json", "srlimit": 3},
            headers=_WIKI_HEADERS,
            timeout=10.0,
        )
        results = resp.json().get("query", {}).get("search", [])
    except Exception:
        return None
    name_lower = name.lower()
    for r in results:
        if any(word in r["title"].lower() for word in name_lower.split() if len(word) > 3):
            return r["title"]
    return None


def _fetch_wikipedia_data(title: str) -> dict:
    """Return {extract, wikipedia_url, website_url} from a Wikipedia page title."""
    result: dict = {}
    try:
        resp = httpx.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{_url_quote(title)}",
            headers=_WIKI_HEADERS,
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            result["extract"] = data.get("extract", "")
            result["wikipedia_url"] = (
                data.get("content_urls", {}).get("desktop", {}).get("page")
            )
    except Exception:
        pass

    # Extract official website from infobox wikitext
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "prop": "revisions", "rvprop": "content",
                    "rvslots": "main", "titles": title, "format": "json"},
            headers=_WIKI_HEADERS,
            timeout=10.0,
        )
        pages = resp.json().get("query", {}).get("pages", {})
        wikitext = (
            next(iter(pages.values()))
            .get("revisions", [{}])[0]
            .get("slots", {}).get("main", {}).get("*", "")
        )
        m = re.search(r'\|\s*website\s*=\s*(.+?)(?:\n|\|)', wikitext, re.IGNORECASE)
        if m:
            url_m = re.search(r'https?://[^\s\|\}\]\n]+', m.group(1))
            if url_m:
                result["website_url"] = url_m.group(0).rstrip("}")
    except Exception:
        pass

    return result


def _generate_venue_description(name: str, extract: str) -> Optional[str]:
    if not extract:
        return None
    llm = get_enrichment_llm()
    try:
        result = llm.invoke(
            f"Summarize the following Wikipedia text about the music venue '{name}' "
            "into one or two concise sentences for a music event listing. "
            "Focus on what kind of venue it is, its history, and what makes it notable.\n\n"
            + extract[:2000]
        )
        return result.content.strip()
    except Exception:
        return None


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
    google_website = place.get("websiteUri")

    # Wikipedia: description + wikipedia_url + website fallback
    wiki_title = _search_wikipedia(venue_name, city)
    wiki_data = _fetch_wikipedia_data(wiki_title) if wiki_title else {}
    description = _generate_venue_description(venue_name, wiki_data.get("extract", ""))
    wikipedia_url = wiki_data.get("wikipedia_url")
    website_url = google_website or wiki_data.get("website_url")

    return {
        "address": place.get("formattedAddress"),
        "website_url": website_url,
        "latitude": lat,
        "longitude": lng,
        "google_place_id": place.get("id"),
        "phone": place.get("nationalPhoneNumber"),
        "google_rating": place.get("rating"),
        "timezone": timezone,
        "description": description,
        "wikipedia_url": wikipedia_url,
    }


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
        "bandcamp_url": None,
        "venue_website": None,
        "address": None,
        "latitude": None,
        "longitude": None,
        "google_place_id": None,
        "phone": None,
        "google_rating": None,
        "timezone": None,
        "venue_description": None,
        "venue_wikipedia_url": None,
    }

    headliner = raw.bands[0] if raw.bands else None
    if headliner:
        band_data = _enrich_band(headliner)
        result["genres"] = band_data["genres"]
        result["spotify_url"] = band_data["spotify_url"]
        result["soundcloud_url"] = band_data["soundcloud_url"]
        result["bandcamp_url"] = band_data["bandcamp_url"]

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
        result["venue_description"] = venue_data.get("description")
        result["venue_wikipedia_url"] = venue_data.get("wikipedia_url")

    return result
