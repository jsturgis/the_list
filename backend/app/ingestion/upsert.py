from __future__ import annotations

"""Persist enriched show dicts to the database (idempotent)."""
import re
from datetime import datetime, time

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ingestion.edition import is_placeholder_website
from app.models.act import Act
from app.models.band import Band
from app.models.show import AgeRestriction, Show, ShowStatus
from app.models.venue import Region, Venue

_DJ_RE = re.compile(r"^dj\s+", re.IGNORECASE)
_B2B_RE = re.compile(r"\s+b2b\s+", re.IGNORECASE)

_CITY_REGION: dict[str, Region] = {
    # SF (incl. Peninsula / San Mateo coast)
    "sf": Region.sf, "s.f.": Region.sf, "san francisco": Region.sf,
    "pacifica": Region.sf, "daly city": Region.sf, "la honda": Region.sf,
    "menlo park": Region.sf, "redwood city": Region.sf, "stanford": Region.sf,
    # East Bay
    "oakland": Region.east_bay, "berkeley": Region.east_bay,
    "albany": Region.east_bay, "alameda": Region.east_bay,
    "walnut creek": Region.east_bay, "concord": Region.east_bay,
    "crockett": Region.east_bay, "san leandro": Region.east_bay,
    "rodeo": Region.east_bay, "orinda": Region.east_bay,
    "emeryville": Region.east_bay, "richmond": Region.east_bay,
    "el cerrito": Region.east_bay, "fremont": Region.east_bay,
    # North Bay
    "petaluma": Region.north_bay, "novato": Region.north_bay,
    "mill valley": Region.north_bay, "sebastopol": Region.north_bay,
    "santa rosa": Region.north_bay, "san rafael": Region.north_bay,
    "napa": Region.north_bay, "fairfax": Region.north_bay,
    "rohnert park": Region.north_bay, "sonoma": Region.north_bay,
    "vallejo": Region.north_bay,
    # South Bay
    "san jose": Region.south_bay, "saratoga": Region.south_bay,
    "sunnyvale": Region.south_bay, "mountain view": Region.south_bay,
    "cupertino": Region.south_bay, "santa clara": Region.south_bay,
    # Santa Cruz
    "santa cruz": Region.santa_cruz, "felton": Region.santa_cruz,
}

_AGE_MAP: dict[str, AgeRestriction] = {
    "a/a": AgeRestriction.all_ages,
    "5+": AgeRestriction.plus_5,
    "6+": AgeRestriction.plus_6,
    "8+": AgeRestriction.plus_8,
    "12+": AgeRestriction.plus_12,
    "13+": AgeRestriction.plus_13,
    "16+": AgeRestriction.plus_16,
    "18+": AgeRestriction.plus_18,
    "21+": AgeRestriction.plus_21,
}


def known_region(city: str | None) -> Region | None:
    """Region for a city in the table, or None (e.g. a Google neighbourhood like "Temescal")."""
    return _CITY_REGION.get(city.lower().strip()) if city else None


def region_for_city(city: str | None) -> Region:
    return known_region(city) or Region.sf


def _age_restriction(s: str | None) -> AgeRestriction:
    if not s:
        return AgeRestriction.unknown
    return _AGE_MAP.get(s.strip(), AgeRestriction.unknown)


def _normalize_price(price_raw: str | None) -> tuple[float | None, float | None, bool]:
    """Return (price_min, price_max, is_free)."""
    if not price_raw:
        return None, None, False
    if price_raw.strip().lower() == "free":
        return 0.0, 0.0, True
    amounts = [float(m) for m in re.findall(r"\$([\d.]+)", price_raw)]
    if not amounts:
        return None, None, False
    return min(amounts), max(amounts), False


def _parse_time(s: str | None) -> time | None:
    if not s:
        return None
    s = s.strip().upper()
    for fmt in ("%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def venue_key(name: str) -> str:
    """Matching key for a Venue name: case-insensitive, ignoring a leading "the" and extra spaces.

    Steve lists the same Venue as both "the Fox Theater" and "Fox Theater".
    """
    key = " ".join(name.lower().split())
    return key[4:] if key.startswith("the ") else key


def find_venue(
    db: Session, name: str, google_place_id: str | None = None, cities: tuple[str | None, ...] = ()
) -> Venue | None:
    """Existing Venue for a listing: same Google place first, then same name (see venue_key).

    A name match must be in a Region one of `cities` belongs to, when any of them is a known city,
    so e.g. Redwood City's "Fox Theater" doesn't merge with Oakland's. Place IDs don't veto a name
    match: the same Venue can come back from Google as a different place.
    """
    if google_place_id:
        venue = (
            db.query(Venue)
            .filter(Venue.google_place_id == google_place_id)
            .order_by(Venue.id)
            .first()
        )
        if venue:
            return venue
    key = venue_key(name)
    q = db.query(Venue).filter(func.lower(Venue.name).in_([key, f"the {key}"]))
    regions = {r for r in map(known_region, cities) if r}
    if regions:
        q = q.filter(Venue.region.in_(regions))
    return q.order_by(Venue.id).first()


def _upsert_venue(db: Session, data: dict) -> Venue:
    name = (data.get("venue_name") or "Unknown Venue").strip()
    place_city = data.get("place_city")
    listing_city = data.get("city")
    venue = find_venue(db, name, data.get("google_place_id"), (listing_city, place_city))
    if not venue:
        city = place_city or listing_city or "Unknown"
        venue = Venue(
            name=name,
            city=city,
            # Google's city can be a neighbourhood outside the table; prefer whichever city is known.
            region=known_region(place_city) or known_region(listing_city) or Region.sf,
        )
        db.add(venue)
        db.flush()
    elif place_city and not venue.city:
        venue.city = place_city
        venue.region = known_region(place_city) or venue.region

    # A placeholder stored by an earlier edition counts as no website, so it's replaced or cleared.
    if is_placeholder_website(venue.website_url):
        venue.website_url = None

    # Apply enrichment fields only when not already set
    for attr, key in [
        ("website_url", "venue_website"),
        ("address", "address"),
        ("google_place_id", "google_place_id"),
        ("timezone", "timezone"),
        ("phone", "phone"),
        ("description", "venue_description"),
        ("wikipedia_url", "venue_wikipedia_url"),
        ("neighborhood", "venue_neighborhood"),
        ("venue_type", "venue_type"),
        ("nearest_transit", "venue_nearest_transit"),
        ("instagram", "venue_instagram"),
        ("image_url", "venue_image_url"),
        ("default_age_restriction", "venue_default_age_restriction"),
    ]:
        if data.get(key) and not getattr(venue, attr):
            setattr(venue, attr, data[key])
    for attr, key in [
        ("latitude", "latitude"),
        ("longitude", "longitude"),
        ("google_rating", "google_rating"),
        ("is_sober_space", "venue_is_sober_space"),
        ("is_cash_only", "venue_is_cash_only"),
        ("membership_required", "venue_membership_required"),
    ]:
        if data.get(key) is not None and getattr(venue, attr) is None:
            setattr(venue, attr, data[key])

    return venue


def _upsert_show(db: Session, venue: Venue, data: dict) -> Show:
    show_date = data["date"]
    door_time = _parse_time(data.get("door_time"))
    door_cond = (
        Show.door_time.is_(None) if door_time is None else Show.door_time == door_time
    )
    show = (
        db.query(Show)
        .filter(Show.date == show_date, Show.venue_id == venue.id, door_cond)
        .first()
    )
    if not show:
        show = Show(date=show_date, venue_id=venue.id, door_time=door_time)
        db.add(show)

    price_min, price_max, is_free = _normalize_price(data.get("price_raw"))
    show.set_time = _parse_time(data.get("set_time"))
    show.price_min = price_min
    show.price_max = price_max
    show.is_free = is_free
    show.age_restriction = _age_restriction(data.get("age_restriction"))
    show.status = ShowStatus(data.get("status", "upcoming"))
    show.is_recommended = bool(data.get("is_recommended"))
    show.will_sell_out = bool(data.get("will_sell_out"))
    show.is_pit = bool(data.get("is_pit"))
    show.is_drink_tickets = bool(data.get("is_drink_tickets"))
    show.is_no_reentry = bool(data.get("is_no_reentry"))
    show.notes = data.get("notes")
    show.is_matinee = bool(data.get("is_matinee"))
    show.is_sold_out = bool(data.get("is_sold_out"))
    show.ticket_provider = data.get("ticket_provider")
    show.ticket_url = data.get("ticket_url") or show.ticket_url  # kept when a later export has none
    show.is_benefit = bool(data.get("is_benefit"))
    show.benefit_cause = data.get("benefit_cause")
    show.special_event = data.get("special_event")
    show.raw_text = data.get("raw_text")
    db.flush()
    return show


def _upsert_acts(db: Session, show: Show, data: dict) -> None:
    band_names = [
        b for b in (data.get("bands") or [])
        if not _DJ_RE.match(b) and not _B2B_RE.search(b) and b.strip()
    ]
    # Steve sometimes repeats a name in the comma-separated lineup
    band_names = list(dict.fromkeys(band_names))
    # Notes are matched by name, since filtering above can shift positions.
    act_notes = dict(zip(data.get("bands") or [], data.get("act_notes") or []))

    # Delete-then-insert keeps position ordering correct on lineup changes
    db.query(Act).filter(Act.show_id == show.id).delete()
    db.flush()

    # Build a lookup of per-band enrichment keyed by name.
    band_enrichment: dict[str, dict] = {}
    for bname, bdata in (data.get("band_enrichment") or []):
        band_enrichment[bname] = bdata
    # Fall back to top-level fields for the headliner when band_enrichment absent.
    if band_names and not band_enrichment and band_names[0] not in band_enrichment:
        band_enrichment[band_names[0]] = {
            "genres": data.get("genres") or [],
            "spotify_url": data.get("spotify_url"),
            "soundcloud_url": data.get("soundcloud_url"),
            "bandcamp_url": data.get("bandcamp_url"),
        }

    for position, name in enumerate(band_names):
        band = db.query(Band).filter(Band.name == name).first()
        if not band:
            band = Band(name=name)
            db.add(band)
            db.flush()

        enrichment = band_enrichment.get(name, {})
        if enrichment.get("genres") and not band.genres:
            band.genres = enrichment["genres"]
        if enrichment.get("spotify_url") and not band.spotify_url:
            band.spotify_url = enrichment["spotify_url"]
        if enrichment.get("soundcloud_url") and not band.soundcloud_url:
            band.soundcloud_url = enrichment["soundcloud_url"]
        if enrichment.get("bandcamp_url") and not band.bandcamp_url:
            band.bandcamp_url = enrichment["bandcamp_url"]
        if enrichment.get("website_url") and not band.website_url:
            band.website_url = enrichment["website_url"]
        if enrichment.get("image_url") and not band.image_url:
            band.image_url = enrichment["image_url"]
            band.image_credit = enrichment.get("image_credit")  # with its photo; None for the edition's
        if enrichment.get("description") and not band.description:
            band.description = enrichment["description"]
        if enrichment.get("mb_links") and not band.links:
            band.links = enrichment["mb_links"]
        if enrichment.get("members") and not band.members:
            band.members = enrichment["members"]
        if enrichment.get("is_local") is not None and band.is_local is None:
            band.is_local = enrichment["is_local"]

        db.add(Act(show_id=show.id, band_id=band.id, position=position, note=act_notes.get(name)))

    db.flush()


def upsert_shows(db: Session, enriched_shows: list[dict]) -> list[Show]:
    """Persist a batch of enriched show dicts. Idempotent."""
    results: list[Show] = []
    for data in enriched_shows:
        venue = _upsert_venue(db, data)
        show = _upsert_show(db, venue, data)
        _upsert_acts(db, show, data)
        results.append(show)
    return results
