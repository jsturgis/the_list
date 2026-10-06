"""Enrichment chain: MusicBrainz genres/URLs, Google Maps venue data, ticket URL."""
from __future__ import annotations

import asyncio
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

_PLACES_FIELD_MASK = "places.formattedAddress,places.addressComponents,places.location,places.websiteUri,places.id,places.nationalPhoneNumber,places.rating,places.utcOffsetMinutes"
_WIKI_HEADERS = {"User-Agent": "the-list/1.0 (https://github.com/jsturgis/the_list) python-httpx"}


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


_MB_WS = "https://musicbrainz.org/ws/2"
_MB_HEADERS = {
    "User-Agent": f"{settings.musicbrainz_app_name}/{settings.musicbrainz_app_version} ( {settings.musicbrainz_contact} )",
}


def _mb_genres(mbid: str) -> list[str]:
    """The artist's MusicBrainz genres, most votes first: the curated genre list, not free-form tags ("seen live",
    "american"). musicbrainzngs can't ask for genres, so this uses the web service directly."""
    _time.sleep(1.0)  # MusicBrainz allows one request a second; musicbrainzngs only paces its own calls
    try:
        resp = httpx.get(f"{_MB_WS}/artist/{mbid}", params={"inc": "genres", "fmt": "json"},
                         headers=_MB_HEADERS, timeout=10.0)
        resp.raise_for_status()
        genres = resp.json().get("genres", [])
    except Exception:
        return []
    return [g["name"] for g in sorted(genres, key=lambda g: -int(g.get("count", 0)))]


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



def _enrich_band(name: str, use_llm: bool = True) -> dict:
    """Return {genres, mb_genres, spotify_url, soundcloud_url, bandcamp_url, website_url} for a band name.

    `genres` are MusicBrainz's curated genres (at most 5), falling back to its top 5 tags when it has none;
    `mb_genres` says whether they're the curated ones. With `use_llm=False` only MusicBrainz is used (no LLM
    guesses for SoundCloud/Bandcamp or genres).
    """
    artist = _mb_search(name)
    if artist is None:
        return {"genres": [], "mb_genres": False, "mbid": None, "spotify_url": None, "soundcloud_url": None,
                "bandcamp_url": None,
                "website_url": None, "links": []}

    full = _mb_lookup(artist["id"])

    tags = sorted(
        full.get("tag-list", []),
        key=lambda t: int(t.get("count", 0)),
        reverse=True,
    )
    curated = _mb_genres(artist["id"])[:5]
    genres = curated or [t["name"] for t in tags[:5]]

    spotify_url: Optional[str] = None
    soundcloud_url: Optional[str] = None
    bandcamp_url: Optional[str] = None
    website_url: Optional[str] = None
    # Every artist-to-URL relationship, kept raw for app/band_links.py to group and rank.
    links = [{"type": rel.get("type", ""), "url": rel["target"]} for rel in full.get("url-relation-list", [])
             if rel.get("target")]
    for rel in full.get("url-relation-list", []):
        target = rel.get("target", "")
        # Matched by host: MusicBrainz's relation types change (Spotify was "streaming music", now "free streaming").
        if not spotify_url and "open.spotify.com/artist/" in target:
            spotify_url = target
        if not soundcloud_url and "soundcloud.com" in target:
            soundcloud_url = target
        if not bandcamp_url and "bandcamp.com" in target:
            bandcamp_url = target
        if not website_url and rel.get("type") == "official homepage":
            website_url = target

    if not use_llm:
        return {"genres": genres, "mb_genres": bool(curated), "mbid": artist["id"], "spotify_url": spotify_url,
                "soundcloud_url": soundcloud_url, "bandcamp_url": bandcamp_url, "website_url": website_url,
                "links": links}

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
        "mb_genres": bool(curated),
        "mbid": artist["id"],
        "spotify_url": spotify_url,
        "soundcloud_url": soundcloud_url,
        "bandcamp_url": bandcamp_url,
        "website_url": website_url,
        "links": links,
    }


# ── Wikipedia ────────────────────────────────────────────────────────────────

def _search_wikipedia(name: str, city: str) -> Optional[str]:
    """Return the Wikipedia page title for a venue, or None if not found.

    Prefers exact title matches over partial ones so e.g. 'The Fillmore'
    beats 'Fillmore District, San Francisco'.
    """
    query = f"{name} {city}"
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": query,
                    "format": "json", "srlimit": 5},
            headers=_WIKI_HEADERS,
            timeout=10.0,
        )
        results = resp.json().get("query", {}).get("search", [])
    except Exception:
        return None

    name_lower = name.lower()
    name_words = [w for w in name_lower.split() if len(w) > 3]
    if not name_words:
        return None

    exact = partial_all = partial_any = None
    for r in results:
        title_lower = r["title"].lower()
        if title_lower == name_lower:
            exact = r["title"]
            break
        if partial_all is None and all(w in title_lower for w in name_words):
            partial_all = r["title"]
            if partial_any is not None:
                break
        elif partial_any is None and any(w in title_lower for w in name_words):
            partial_any = r["title"]

    return exact or partial_all or partial_any


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
            "Focus on what kind of venue it is, its history, and what makes it notable. "
            "If the article is not about this venue or is clearly inaccurate, reply with only the word 'SKIP'. "
            "Reply with only the summary — do not include any commentary, preamble, or explanation.\n\n"
            + extract[:2000]
        )
        text = result.content.strip()
        return None if text.upper() == "SKIP" else text
    except Exception:
        return None


# ── Venue name cleaning ───────────────────────────────────────────────────────

@lru_cache(maxsize=512)
def _clean_venue_name(raw_name: str) -> str:
    """Use LLM to strip city names, age restrictions, etc. from a parsed venue name."""
    llm = get_enrichment_llm()
    try:
        result = llm.invoke(
            "Extract only the venue name from the string below, removing any city names, "
            "neighborhoods, age restrictions (e.g. '21+', '18+', 'A/A'), or other details. "
            "Reply with ONLY the venue name, nothing else.\n\n"
            "Examples:\n"
            "  'the Ivy Room Albany 21+' → 'the Ivy Room'\n"
            "  '924 Gilman Street Berkeley' → '924 Gilman Street'\n"
            "  'The Chapel SF' → 'The Chapel'\n"
            "  'Bottom of the Hill SF 18+' → 'Bottom of the Hill'\n\n"
            f"Input: '{raw_name}'"
        )
        cleaned = result.content.strip().strip("'\"")
        return cleaned if cleaned else raw_name
    except Exception:
        return raw_name


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
def _enrich_venue(venue_name: str, city: str, street: str | None = None, use_llm: bool = True) -> dict:
    """Return venue enrichment dict from Google Places + Timezone APIs, or {}.

    `street` (when the listing gave one) narrows the search for generic names like "Music Hall".
    With `use_llm=False` (names already clean, e.g. from a formatted edition) there are no LLM calls:
    the name is searched as given, and the Wikipedia description is skipped because without the LLM
    there's nothing to confirm the Wikipedia article is about this Venue.
    """
    api_key = settings.google_maps_api_key
    if not api_key:
        return {}
    clean_name = _clean_venue_name(venue_name) if use_llm else venue_name
    try:
        resp = httpx.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _PLACES_FIELD_MASK},
            json={"textQuery": " ".join(p for p in (clean_name, street, city) if p)},
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
    _CITY_TYPES = {"locality", "administrative_area_level_3", "sublocality", "sublocality_level_1"}
    place_city = next(
        (c.get("longText") for c in place.get("addressComponents", [])
         if _CITY_TYPES & set(c.get("types", []))),
        None,
    )

    # Wikipedia: description + wikipedia_url + website fallback (needs the LLM to validate the match)
    wiki_title = _search_wikipedia(clean_name, city) if use_llm else None
    wiki_data = _fetch_wikipedia_data(wiki_title) if wiki_title else {}
    description = _generate_venue_description(clean_name, wiki_data.get("extract", "")) if use_llm else None
    # A None description means the LLM flagged the Wikipedia match as wrong (SKIP)
    # or the extract was empty — discard the URL so a bad match doesn't persist.
    wikipedia_url = wiki_data.get("wikipedia_url") if description else None
    website_url = google_website or (wiki_data.get("website_url") if description else None)

    return {
        "address": place.get("formattedAddress"),
        "city": place_city,
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
        "place_city": None,
    }

    loop = asyncio.get_event_loop()

    if raw.bands:
        # Enrich all bands concurrently so each gets its own URLs/genres.
        all_band_data = await asyncio.gather(
            *[loop.run_in_executor(None, _enrich_band, name) for name in raw.bands]
        )
        headliner_data = all_band_data[0]
        result["genres"] = headliner_data["genres"]
        result["spotify_url"] = headliner_data["spotify_url"]
        result["soundcloud_url"] = headliner_data["soundcloud_url"]
        result["bandcamp_url"] = headliner_data["bandcamp_url"]
        result["band_enrichment"] = list(zip(raw.bands, all_band_data))

        # If headliner has no genres, use the first supporting act that does.
        if not result["genres"]:
            for _, band_data in list(zip(raw.bands, all_band_data))[1:]:
                if band_data["genres"]:
                    result["genres"] = band_data["genres"]
                    break

    if raw.venue_name:
        venue_data = await loop.run_in_executor(
            None, _enrich_venue, raw.venue_name, raw.city or "", raw.venue_address
        )
        listed_address = ", ".join(p for p in (raw.venue_address, raw.city) if p) if raw.venue_address else None
        result["address"] = venue_data.get("address") or listed_address
        result["venue_website"] = venue_data.get("website_url")
        result["latitude"] = venue_data.get("latitude")
        result["longitude"] = venue_data.get("longitude")
        result["google_place_id"] = venue_data.get("google_place_id")
        result["phone"] = venue_data.get("phone")
        result["google_rating"] = venue_data.get("google_rating")
        result["timezone"] = venue_data.get("timezone")
        result["venue_description"] = venue_data.get("description")
        result["venue_wikipedia_url"] = venue_data.get("wikipedia_url")
        result["place_city"] = venue_data.get("city")

    return result
