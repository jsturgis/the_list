"""Enrichment chain: MusicBrainz genres/URLs, Google Maps venue data, ticket URL."""
from __future__ import annotations

import re
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
_MAPS_FIELDS = "formatted_address,geometry,website,place_id"
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


def _enrich_band(name: str) -> dict:
    """Return {genres, spotify_url, soundcloud_url} for a band name."""
    artist = _mb_search(name)
    if artist is None:
        return {"genres": [], "spotify_url": None, "soundcloud_url": None}

    full = _mb_lookup(artist["id"])

    tags = sorted(
        full.get("tag-list", []),
        key=lambda t: int(t.get("count", 0)),
        reverse=True,
    )
    genres = [t["name"] for t in tags[:5]]

    spotify_url: Optional[str] = None
    soundcloud_url: Optional[str] = None
    for rel in full.get("url-relation-list", []):
        target = rel.get("target", "")
        rel_type = rel.get("type", "")
        if not spotify_url and "spotify.com" in target and rel_type == "streaming music":
            spotify_url = target
        if not soundcloud_url and "soundcloud.com" in target:
            soundcloud_url = target

    # LLM fallback: genres empty + SoundCloud page available to scrape
    if not genres and soundcloud_url:
        scraped = _scrape_text(soundcloud_url)
        if scraped:
            genres = _extract_genres_via_llm(scraped)

    return {"genres": genres, "spotify_url": spotify_url, "soundcloud_url": soundcloud_url}


# ── Google Maps ───────────────────────────────────────────────────────────────

def _enrich_venue(venue_name: str, city: str) -> dict:
    """Return {address, website_url, latitude, longitude, google_place_id} or {}."""
    api_key = settings.google_maps_api_key
    if not api_key:
        return {}
    try:
        resp = httpx.get(
            "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
            params={
                "input": f"{venue_name} {city}",
                "inputtype": "textquery",
                "fields": _MAPS_FIELDS,
                "key": api_key,
            },
            timeout=10.0,
        )
        data = resp.json()
    except Exception:
        return {}

    candidates = data.get("candidates", [])
    if not candidates:
        return {}

    place = candidates[0]
    loc = place.get("geometry", {}).get("location", {})
    return {
        "address": place.get("formatted_address"),
        "website_url": place.get("website"),
        "latitude": loc.get("lat"),
        "longitude": loc.get("lng"),
        "google_place_id": place.get("place_id"),
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
        "venue_website": None,
        "address": None,
        "latitude": None,
        "longitude": None,
        "google_place_id": None,
        "ticket_url": None,
    }

    headliner = raw.bands[0] if raw.bands else None
    if headliner:
        band_data = _enrich_band(headliner)
        result["genres"] = band_data["genres"]
        result["spotify_url"] = band_data["spotify_url"]
        result["soundcloud_url"] = band_data["soundcloud_url"]

    if raw.venue_name:
        venue_data = _enrich_venue(raw.venue_name, raw.city or "")
        result["address"] = venue_data.get("address")
        result["venue_website"] = venue_data.get("website_url")
        result["latitude"] = venue_data.get("latitude")
        result["longitude"] = venue_data.get("longitude")
        result["google_place_id"] = venue_data.get("google_place_id")

    is_free = (raw.price_raw or "").strip().lower() == "free"
    if not is_free and headliner:
        result["ticket_url"] = _find_ticket_url(result["venue_website"], headliner)

    return result
