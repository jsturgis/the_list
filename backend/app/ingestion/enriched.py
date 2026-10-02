"""Fill gaps in a formatted edition from the enriched List export.

The enriched export ("San Francisco Area Music List for <date>.enriched.json") is a top-level list
of schema v2.0.0 events, like the formatted edition's `events`. It is more complete for Venue data
(coordinates, images, Instagram, transit), ticket links, Show notes and artist images and descriptions,
but weaker on artist links and genres, so only those fields are taken, and only where the formatted
edition has none. The formatted edition stays the source of which Shows exist.
"""
from __future__ import annotations

import re

from app.ingestion.edition import _text, edition_shows
from app.ingestion.upsert import venue_key

_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_ARTIST_NOTE_RE = re.compile(r"\s*\(.*?\)\s*$")
# What the tool that makes the enriched export says about its own work, not about the Band.
_TOOL_REMARKS = {"added during enrichment"}
_SHOW_FIELDS = ("latitude", "longitude", "venue_image_url", "venue_instagram", "venue_nearest_transit",
                "ticket_url")


def merge_enriched(shows_data: list[dict], enriched_events: list[dict]) -> int:
    """Fill empty fields of `shows_data` (from `edition_shows`) in place; return how many Shows matched."""
    events = [e for e in enriched_events if isinstance(e, dict) and e.get("artists")]
    by_date: dict = {}
    for enriched_show, event in zip(edition_shows({"events": events}), events):
        by_date.setdefault(enriched_show["date"], []).append((enriched_show, event))
    matched = 0
    for data in shows_data:
        found = _match(data, by_date.get(data["date"], []))
        if not found:
            continue
        enriched_show, event = found
        matched += 1
        for field in _SHOW_FIELDS:
            if data.get(field) is None and enriched_show.get(field) is not None:
                data[field] = enriched_show[field]
        _add_note(data, enriched_show.get("special_event"))
        _merge_artists(data, event.get("artists") or [])
    return matched


def _add_note(data: dict, note: str | None) -> None:
    """Append the enriched "special event" to the Show's notes, unless they already say it.

    It's often a remark rather than an event name ("show itself not independently confirmed"; "6pm-midnight;
    $10-$50 sliding scale"), so it isn't used as the Show's special event.
    """
    if not note:
        return
    notes = data.get("notes")
    if notes and note.lower() in notes.lower():
        return
    data["notes"] = f"{notes}; {note}" if notes else note


def _match(data: dict, candidates: list[tuple[dict, dict]]) -> tuple[dict, dict] | None:
    """The one enriched Show at the same Venue on the same date, or None when there's none or it's unclear.

    Names match when equal after normalising (see _venue_words), else when one is the start of the other
    ("Hotel Utah Saloon" and "Hotel Utah"). Several Shows at the Venue that day are told apart by door time.
    """
    words = _venue_words(data["venue_name"])
    if not words:
        return None
    at_venue = [c for c in candidates if _venue_words(c[0]["venue_name"]) == words]
    if not at_venue:
        at_venue = [c for c in candidates if _starts_with(_venue_words(c[0]["venue_name"]), words)]
    if len(at_venue) > 1:
        at_venue = [c for c in at_venue if c[0]["door_time"] == data["door_time"]]
    return at_venue[0] if len(at_venue) == 1 else None


def _venue_words(name: str | None) -> tuple[str, ...]:
    """"The Brick & Mortar Music Hall" -> ("brick", "and", "mortar", "music", "hall")."""
    return _words(venue_key(name or "").replace("theatre", "theater"))


def _artist_words(name: str | None) -> tuple[str, ...]:
    """"Ilana Glazer (comedian)" -> ("ilana", "glazer"); "Mt. Jones" -> ("mt", "jones")."""
    return _words(_ARTIST_NOTE_RE.sub("", name or ""))


def _words(text: str) -> tuple[str, ...]:
    return tuple(_PUNCTUATION_RE.sub("", text.lower().replace("&", " and ")).split())


def _starts_with(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    shorter, longer = sorted((a, b), key=len)
    return bool(shorter) and longer[:len(shorter)] == shorter


def _merge_artists(data: dict, artists: list[dict]) -> None:
    """Artist images and descriptions, matched by name (see _artist_words). Links and genres aren't taken.

    An artist's note describes the Band ("Bilingual metal band from Fairfield ..."), so it becomes the
    Band's description, not an act note on the Show.
    """
    by_name = {_artist_words(a.get("name")): a for a in artists}
    for name, enrichment in data["band_enrichment"]:
        artist = by_name.get(_artist_words(name))
        if not artist:
            continue
        image_url = _text(artist.get("image_url"))
        if image_url and not enrichment.get("image_url"):
            enrichment["image_url"] = image_url
        note = _text(artist.get("note"))
        if note and note.lower() not in _TOOL_REMARKS and not enrichment.get("description"):
            enrichment["description"] = note
