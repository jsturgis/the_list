from __future__ import annotations

"""Persist enriched show dicts to the database (idempotent)."""
import difflib
import logging
import re
from datetime import date, datetime, time
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.slugs import slugify
from app.models.act import Act
from app.models.band import Band
from app.models.show import AgeRestriction, Show, ShowStatus
from app.models.venue import Region, Venue

logger = logging.getLogger(__name__)

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


# Other names Steve lists a Venue under (a short name, a typo, an older name, a room within it), and the
# name the Venue goes by here. Listings under these names join that Venue instead of starting a new one.
# Names are compared by key (see _name_key), so case, a leading "the", punctuation and theater/theatre don't count.
_VENUE_ALIASES: dict[str, str] = {
    "castro": "The Castro Theatre",
    "kilowatt": "Kilowatt Bar",
    "warriors stadium": "Chase Center (Warriors Stadium)",
    "hotel utah": "Hotel Utah Saloon",
    "catalyst atrium": "The Catalyst",  # a room within it
    "brick and mortar": "Brick & Mortar Music Hall",
    "on broadway at mabuhay gardens": "Mabuhay Gardens",
    "subrosa": "Subrosa Community Space",
    "fml studios": "FML Studio",
    "club, napa music hall": "Napa Music Hall",
    "924 gilman": "924 Gilman Street",
    "924 gilman st": "924 Gilman Street",
    "freight": "Freight & Salvage",
    "starry plough": "The Starry Plough Pub",
    "shark tank": "SAP Center (Shark Tank)",
    "towne cycles": "Towne Cycles Backyard",
    "9 lives": "9 Lives Warehouse",
    "vinnies": "Vinnie's Bar",
    "kuumbwa": "Kuumbwa Jazz Center",
    "gilman brewery company": "Gilman Brewing Co.",
    "49s stadium": "the 49'er Stadium",
    "greek theater": "Greek Theatre (UC Berkeley)",
    "hotel utan": "Hotel Utah Saloon",
    "mabuhauy gardens": "Mabuhay Gardens",
    "on broadway": "Mabuhay Gardens",  # upstairs in the same building; Steve lists one Show under both
    "blue note napa": "Napa Music Hall",
    "3rd and army skatepark": "3rd and Army",
    "x sports bar": "The X-Bar",
    "shed a, pier 48": "Pier 48",
    "lanesplitters pizza": "Lanesplitter Pizza",
    "point san pablo harbor": "the Knot Club",  # the club at the harbor
    "brodway hall": "Broadway Hall",
}
# Names that are a different Venue in each city, by (name, city): Steve's "Hopmonk" is two taverns.
_VENUE_ALIASES_IN_CITY: dict[tuple[str, str], str] = {
    ("hopmonk", "novato"): "HopMonk Tavern (Novato)",
    ("hopmonk tavern", "novato"): "HopMonk Tavern (Novato)",
    ("hopmonk", "sebastopol"): "HopMonk Tavern (Sebastopol)",
    ("hopmonk tavern", "sebastopol"): "HopMonk Tavern (Sebastopol)",
    ("arena", "oakland"): "Oakland Arena",
    ("civic auditorium", "san francisco"): "Bill Graham Civic Auditorium",
    ("civic auditorium", "san jose"): "San Jose Civic Center",
    ("civic center", "san jose"): "San Jose Civic Center",
    ("streetlight records", "santa cruz"): "Streetlight Records (Santa Cruz)",
    ("amoeba music", "san francisco"): "Amoeba",
    ("music hall", "felton"): "Felton Music Hall",
    ("pavilion", "concord"): "Toyota Pavilion at Concord",
}
# How alike two name keys must be for one to be a typo of the other ("the Indpendent", "the Ivy Roomm"), and
# the shortest key that's matched that way.
_TYPO_SIMILARITY = 0.9
_TYPO_MIN_LENGTH = 6
# Steve's own site, stored as a Venue's website by early editions that didn't know the Venue's.
_PLACEHOLDER_WEBSITE_HOST = "stevelist.com"


def is_placeholder_website(url: str | None) -> bool:
    """Whether a Venue website is a stand-in (Steve's own site) rather than the Venue's."""
    host = urlparse(url).netloc.lower() if url else ""
    return host == _PLACEHOLDER_WEBSITE_HOST or host.endswith("." + _PLACEHOLDER_WEBSITE_HOST)


def _name_key(name: str) -> str:
    """A Venue name without what Steve varies: case, a leading "the", "&" for "and", apostrophes, full stops and
    hyphens, "theatre" for "theater", extra spaces."""
    key = name.lower().replace("&", " and ").replace("theatre", "theater")
    key = " ".join(re.sub(r"[.'’\-]", "", key).split())
    return key[4:] if key.startswith("the ") else key


def canonical_venue_name(name: str, city: str | None = None) -> str:
    """The name a Venue goes by: the usual name for a known variant (see _VENUE_ALIASES, and _VENUE_ALIASES_IN_CITY
    for a variant that depends on the listing's `city`), else the name as given."""
    key = _name_key(name)
    in_city = _VENUE_ALIASES_IN_CITY.get((key, " ".join(city.lower().split()))) if city else None
    return in_city or _VENUE_ALIASES.get(key, name)


def venue_key(name: str, city: str | None = None) -> str:
    """Matching key for a Venue name (see _name_key), with a known variant read as the Venue's usual name.

    Steve lists the same Venue as both "the Fox Theater" and "Fox Theater", "the UC Theater" for The UC Theatre,
    and "Hotel Utah Saloon" as "Hotel Utan".
    """
    return _name_key(canonical_venue_name(name, city))


def band_key(name: str) -> str:
    """Matching key for a Band name: its slug (app.slugs), so case, accents, apostrophes and punctuation don't count
    and "&" is "and". Steve lists the same Band as "Swept To Sea" and "Swept to Sea", "B.F.H" and "B.F.H.".
    Empty for a name with no letters or digits, which then matches only itself.
    """
    return slugify(name)


def find_band(db: Session, name: str) -> Band | None:
    """Existing Band with this name, else the first (lowest id) with the same key (see band_key), else the one
    listed under this spelling before a service put it right (Band.spellings: "Sunamo" is Sunami)."""
    band = db.query(Band).filter(Band.name == name).first()
    key = band_key(name)
    if band or not key:
        return band
    # Only new names get here, a few per edition, so scanning every name is cheap.
    rows = db.query(Band.id, Band.name, Band.spellings).order_by(Band.id).all()
    ids = [id_ for id_, other, _ in rows if band_key(other) == key] or \
          [id_ for id_, _, spellings in rows if any(band_key(s) == key for s in spellings or [])]
    return db.get(Band, ids[0]) if ids else None


def find_venue(
    db: Session, name: str, google_place_id: str | None = None, cities: tuple[str | None, ...] = ()
) -> Venue | None:
    """Existing Venue for a listing: same Google place first, then same name (see venue_key).

    A name match must be in a Region one of `cities` belongs to, when any of them is a known city,
    so e.g. Redwood City's "Fox Theater" doesn't merge with Oakland's. Place IDs don't veto a name
    match: the same Venue can come back from Google as a different place.

    A name the Venue was listed under before and matched through its Google place (Venue.spellings) counts as one
    of its names, after its own.

    A known variant name (see _VENUE_ALIASES) is matched by name first: Google places a misspelt or
    renamed Venue somewhere else, and that place can be another Venue's. The first of `cities` is the listing's.

    Last, a name one typo away from a Venue's, or from a known variant ("the Indpendent", "the eCastro").
    """
    city = cities[0] if cities else None
    key = venue_key(name, city)
    candidates = db.query(Venue)
    regions = {r for r in map(known_region, cities) if r}
    if regions:
        candidates = candidates.filter(Venue.region.in_(regions))
    # Compared here rather than in SQL, as keys aren't how names are stored; there are a few hundred Venues.
    by_key: dict[str, Venue] = {}
    ordered = candidates.order_by(Venue.id).all()
    for candidate in ordered:
        by_key.setdefault(_name_key(candidate.name), candidate)
    for candidate in ordered:
        for spelling in candidate.spellings or []:
            by_key.setdefault(_name_key(spelling), candidate)

    if canonical_venue_name(name, city) != name and key in by_key:
        return by_key[key]
    if google_place_id:
        venue = (
            db.query(Venue)
            .filter(Venue.google_place_id == google_place_id)
            .order_by(Venue.id)
            .first()
        )
        if venue:
            return venue
    if key in by_key:
        return by_key[key]
    if len(key) < _TYPO_MIN_LENGTH:
        return None
    aliases = {alias: _name_key(usual) for alias, usual in _VENUE_ALIASES.items()}
    close = difflib.get_close_matches(key, [*by_key, *aliases], n=1, cutoff=_TYPO_SIMILARITY)
    return by_key.get(aliases.get(close[0], close[0])) if close else None


def _upsert_venue(db: Session, data: dict) -> Venue:
    name = (data.get("venue_name") or "Unknown Venue").strip()
    place_city = data.get("place_city")
    listing_city = data.get("city")
    venue = find_venue(db, name, data.get("google_place_id"), (listing_city, place_city))
    if not venue:
        city = place_city or listing_city or "Unknown"
        venue = Venue(
            name=canonical_venue_name(name, listing_city),
            city=city,
            # Google's city can be a neighbourhood outside the table; prefer whichever city is known.
            region=known_region(place_city) or known_region(listing_city) or Region.sf,
        )
        db.add(venue)
        db.flush()
    else:
        if place_city and not venue.city:
            venue.city = place_city
            venue.region = known_region(place_city) or venue.region
        # Matched only through its Google place: keep the listed name, so the next listing under it is known by
        # name and not looked up on Google Places again (scheduler.ingest_shows).
        if (venue_key(name, listing_city) != _name_key(venue.name) and name not in (venue.spellings or [])
                and find_venue(db, name, None, (listing_city,)) is not venue):
            venue.spellings = [*(venue.spellings or []), name]

    # A placeholder stored by an early edition counts as no website, so it's replaced or cleared.
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

    db.flush()   # so the next listing's lookup sees it (its Google place id above all)
    return venue


def _listed_bands(data: dict) -> list[str]:
    """The listing's Bands: its lineup without DJs, back-to-back sets and blanks."""
    return [b for b in (data.get("bands") or []) if not _DJ_RE.match(b) and not _B2B_RE.search(b) and b.strip()]


def _headliner(names: list[str]) -> str | None:
    """Matching key for the first of these Band names (see band_key), or None when there are none."""
    return (band_key(names[0]) or names[0]) if names else None


def _show_headliner(show: Show) -> str | None:
    """Matching key for the Show's headliner (its first Act's Band, see band_key), or None when it has no Acts."""
    return _headliner([a.band.name for a in sorted(show.acts, key=lambda a: a.position)])


def _find_shows(db: Session, date_: date, venue_id: int, door_time: time | None) -> list[Show]:
    """The stored Shows with this identity (date, Venue and door time), oldest first. Usually one; a Venue with two
    rooms has a Show in each at the same time."""
    door_cond = Show.door_time.is_(None) if door_time is None else Show.door_time == door_time
    return db.query(Show).filter(Show.date == date_, Show.venue_id == venue_id, door_cond).order_by(Show.id).all()


def _claim_shows(slots: list[tuple], shows: list[Show]) -> dict[tuple, Show]:
    """Which of `shows` (stored Shows with one identity) each slot (the listings with that identity, one slot per
    headliner) is: the Show with the slot's headliner first, then, in order, the Shows left to the slots left. So
    a lone listing whose headliner Steve corrected still updates its Show, and when a Show stored before two rooms'
    listings were told apart has the second room's lineup, that room keeps it and the first gets a new Show.
    When several headliners at one identity change in the same run, the leftovers are paired in page order; the
    next run finds each Show by its headliner."""
    free = list(shows)
    claimed: dict[tuple, Show] = {}
    for slot in slots:
        show = next((s for s in free if _show_headliner(s) == slot[-1]), None)
        if show:
            free.remove(show)
            claimed[slot] = show
    for slot, show in zip([slot for slot in slots if slot not in claimed], free):
        claimed[slot] = show
    return claimed


def _find_changed_show(db: Session, venue: Venue, data: dict, taken: set[int]) -> Show | None:
    """The stored Show a listing is about when its door time isn't the Show's: Steve adds a time he didn't have,
    corrects one, or drops them ("POSTPONED: Francisca Valenzuela at Rickshaw Stop, S.F.").

    It's the one Show at the Venue that day with the listing's headliner, or, for a listing that names no Band and
    no time ("INCORRECT LISTING: dj Raphi at August Hall"), the only Show there that day. Shows in `taken` are
    other listings' (an early and a late show by one headliner are two Shows), and when it's unclear which Show is
    meant there's no match.
    """
    candidates = [s for s in db.query(Show).filter(Show.date == data["date"], Show.venue_id == venue.id)
                  if s.id not in taken]
    bands = _listed_bands(data)
    if bands:
        headliner = _headliner(bands)
        candidates = [s for s in candidates if s.acts and _show_headliner(s) == headliner]
    elif data.get("door_time"):
        return None
    return candidates[0] if len(candidates) == 1 else None


def _upsert_show(db: Session, venue: Venue, data: dict, show: Show | None) -> Show:
    """Store the listing as `show` (found by _claim_shows or _find_changed_show), or as a new Show."""
    door_time = _parse_time(data.get("door_time"))
    if not show:
        show = Show(date=data["date"], venue_id=venue.id, door_time=door_time)
        db.add(show)
    elif door_time is not None:
        show.door_time = door_time   # a changed Show takes the listing's time; one listed without a time keeps its own

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
    # A benefit stays one: Shows ingested before the List was read from Steve's page say so in fields it doesn't have.
    show.is_benefit = bool(data.get("is_benefit") or show.is_benefit)
    # The List doesn't say these; what a Show already has (from those earlier editions) is kept.
    for field in ("ticket_provider", "ticket_url", "benefit_cause", "special_event"):
        if data.get(field):
            setattr(show, field, data[field])
    show.raw_text = data.get("raw_text")
    # Where the Show is listed: a Show added from an event page becomes the List's once Steve lists it.
    show.source = data.get("source", "list")
    db.flush()
    return show


def _upsert_acts(db: Session, show: Show, data: dict) -> None:
    band_names = _listed_bands(data)
    # Steve sometimes repeats a name in the comma-separated lineup, not always spelled the same (see band_key)
    first_spelling: dict[str, str] = {}
    for b in band_names:
        first_spelling.setdefault(band_key(b) or b, b)
    band_names = list(first_spelling.values())
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
        band = find_band(db, name)
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
    db.expire(show, ["acts"])   # the Acts were replaced by id, so a lineup loaded earlier is stale


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


# Listings of one headliner at a Venue on a day whose door times are less than this far apart are one Show: Steve
# lists it twice, once as "7pm/8pm" and once as just "8pm". An early and a late show are at least this far apart
# (7pm and 9pm).
_SAME_SHOW_MINUTES = 120


def _details(data: dict) -> int:
    """How much a listing says about its Show: times and price."""
    return sum(bool(data.get(field)) for field in ("door_time", "set_time", "price_raw"))


def _one_listing_per_show(venues: list[Venue], enriched_shows: list[dict]) -> list[int]:
    """Indexes of the listings to store, in page order: of two with the same date, Venue and headliner and door
    times less than _SAME_SHOW_MINUTES apart, only the one that says more (the later, when they say as much,
    as a repeated line has always been).
    Listings without a time or a Band are all kept."""
    kept: list[int] = []
    for i, (venue, data) in enumerate(zip(venues, enriched_shows)):
        door, headliner = _parse_time(data.get("door_time")), _headliner(_listed_bands(data))
        same = None
        if door is not None and headliner is not None:
            same = next((k for k in kept
                         if (enriched_shows[k]["date"], venues[k].id) == (data["date"], venue.id)
                         and _headliner(_listed_bands(enriched_shows[k])) == headliner
                         and (other := _parse_time(enriched_shows[k].get("door_time"))) is not None
                         and abs(_minutes(other) - _minutes(door)) < _SAME_SHOW_MINUTES), None)
        if same is None:
            kept.append(i)
        elif _details(data) >= _details(enriched_shows[same]):
            kept[kept.index(same)] = i
    return sorted(kept)


def upsert_shows(db: Session, enriched_shows: list[dict]) -> list[Show]:
    """Persist a batch of enriched show dicts. Idempotent.

    A Show's identity is its date, Venue and door time, and its headliner tells apart the Shows that share one: a
    Venue with two rooms lists a Show in each at the same time ("(upstairs)", "(downstairs)"). Listings with the
    same identity and headliner are one Show (Steve repeats a line), and so are a headliner's listings at the Venue
    that day with door times less than two hours apart (see _one_listing_per_show). Each listing is, in turn:

    - a stored Show with its identity: the one with its headliner, else one left over once the other listings with
      that identity have taken theirs (see _claim_shows). A lone listing with an identity is that identity's Show
      whatever its headliner, so a corrected lineup updates its Show;
    - failing that, the stored Show whose time it changes (see _find_changed_show), among those no other listing
      has claimed;
    - failing that, a new Show.

    A cancelled or postponed listing that names no Band and matches no Show isn't stored: there's nothing to cancel,
    and nothing to show.
    """
    venues = [_upsert_venue(db, data) for data in enriched_shows]
    kept = _one_listing_per_show(venues, enriched_shows)
    venues, enriched_shows = [venues[i] for i in kept], [enriched_shows[i] for i in kept]
    slots = [(data["date"], venue.id, _parse_time(data.get("door_time")), _headliner(_listed_bands(data)))
             for venue, data in zip(venues, enriched_shows)]
    by_identity: dict[tuple, list[tuple]] = {}
    for slot in slots:
        same = by_identity.setdefault(slot[:3], [])
        if slot not in same:
            same.append(slot)
    claimed: dict[tuple, Show] = {}
    for identity, same in by_identity.items():
        claimed.update(_claim_shows(same, _find_shows(db, *identity)))
    taken = {show.id for show in claimed.values()}

    results: list[Show] = []
    for venue, data, slot in zip(venues, enriched_shows, slots):
        # An earlier listing in this batch may have just stored the slot's Show (Steve repeats a line).
        show = claimed.get(slot) or _find_changed_show(db, venue, data, taken)
        bands = _listed_bands(data)
        if data.get("source", "list") != "list" and show is not None and show.source == "list":
            if _show_headliner(show) != slot[3]:
                show = None   # another Show at that time (the other room): an event from elsewhere isn't a correction
            else:
                # The List wins: Steve's Show stays as he lists it, and only takes the event's ticket link.
                for field in ("ticket_provider", "ticket_url"):
                    if data.get(field):
                        setattr(show, field, data[field])
                db.flush()
                taken.add(show.id)
                claimed[slot] = show
                results.append(show)
                continue
        if show is None and not bands and data.get("status", "upcoming") != "upcoming":
            continue
        kept_lineup = bool(show and not bands and show.acts)
        show = _upsert_show(db, venue, data, show)
        taken.add(show.id)
        claimed[slot] = show
        if not kept_lineup:   # a listing that names no Band doesn't empty a stored Show's lineup
            _upsert_acts(db, show, data)
        results.append(show)
    return results


# More than this share of the List's stored Shows gone from one page isn't Steve's corrections: a page that has
# changed shape, or listings this code no longer reads. Nothing is removed then.
_MAX_UNLISTED_SHARE = 0.1


def remove_unlisted_shows(db: Session, listed: list[Show], since: date) -> list[int]:
    """Delete the List's Shows on or after `since` (the page's first date) that none of its listings is, now that
    `listed` (what upsert_shows returned for the whole page) are. Returns their ids.

    Steve's page lists every upcoming Show, so a stored one it doesn't list is gone from it: a copy kept when a
    listing changed in a way upsert_shows couldn't follow (a time added before a Show could take one; a headliner
    the old edition misread), a Show moved to another Venue or day, or one Steve took down. Shows from elsewhere
    (an event page, a Venue's calendar) aren't the List's to remove. A copy's old-edition details go to the one
    listed Show at its Venue that day with its headliner, when there is one. When too many would go (see
    _MAX_UNLISTED_SHARE), none are.
    """
    listed_ids = {show.id for show in listed}
    stored = db.query(Show).filter(Show.date >= since, Show.source == "list").all()
    unlisted = [show for show in stored if show.id not in listed_ids]
    if len(unlisted) > _MAX_UNLISTED_SHARE * len(stored):
        logger.warning("ingestion: %d of the %d stored Shows from %s on aren't on the page; kept them all",
                       len(unlisted), len(stored), since)
        return []
    for show in unlisted:
        same = [s for s in listed if (s.date, s.venue_id) == (show.date, show.venue_id)
                and s.acts and _show_headliner(s) == _show_headliner(show)]
        if len(same) == 1:
            _keep_edition_details(show, same[0])
        db.delete(show)
    db.flush()
    return [show.id for show in unlisted]


def same_event(added: Show, listed: Show) -> bool:
    """Whether two Shows at one Venue on one day are one event listed twice, spelled differently: their headliners are
    one Band misspelt (as close as a Venue's typo, _TYPO_SIMILARITY: "Sunamo" and "Sunami" aren't, at 0.83), or half
    the shorter lineup, at least two Bands, is the same Bands ("Sunamo with No Pressure, Outta Pocket, Middrift, Small
    Crush..." and "Sunami with No Pressure, Midrift, Outta Pocket, Small Crush...")."""
    if (added.date, added.venue_id) != (listed.date, listed.venue_id) or not added.acts or not listed.acts:
        return False
    first, second = _show_headliner(added), _show_headliner(listed)
    if first == second or difflib.SequenceMatcher(None, first, second).ratio() >= _TYPO_SIMILARITY:
        return True
    keys = [{band_key(a.band.name) or a.band.name for a in show.acts} for show in (added, listed)]
    shorter = min(len(k) for k in keys)
    return shorter >= 2 and len(keys[0] & keys[1]) * 2 >= shorter


def fold_added_shows(db: Session, shows: list[Show]) -> tuple[list[Show], list[int]]:
    """Fold each Show from elsewhere (an event page, a screenshot) into the List's Show of the same event (see
    same_event), whichever of `shows` was just stored: the List wins, as when the headliner is spelled the same (see
    upsert_shows). The List's Show keeps its lineup and details and takes the other's ticket link if it has none; the
    other is deleted. When the event is two of the List's Shows (an early and a late one), only the one at the same
    door time takes it, and with none, nothing is folded.

    Returns `shows` with each folded Show replaced by the List's, and the ids deleted."""
    folded: dict[int, Show] = {}
    for show in shows:
        others = [s for s in db.query(Show).filter(Show.date == show.date, Show.venue_id == show.venue_id)
                  if s.id != show.id and s.id not in folded]
        if show.source == "list":
            pairs = [(other, show) for other in others if other.source != "list"]
        else:
            pairs = [(show, other) for other in others if other.source == "list"]
        for added, listed in pairs:
            if added.id in folded or not same_event(added, listed):
                continue
            rivals = [s for s in db.query(Show).filter(Show.date == added.date, Show.venue_id == added.venue_id,
                                                       Show.source == "list") if same_event(added, s)]
            if len(rivals) > 1 and listed.door_time != added.door_time:
                continue   # which of the List's Shows it is isn't clear
            if added.ticket_url and not listed.ticket_url:
                listed.ticket_url, listed.ticket_provider = added.ticket_url, added.ticket_provider
            logger.info("ingestion: show %d (%s) is the List's show %d; folded into it", added.id, added.source,
                        listed.id)
            folded[added.id] = listed
            db.delete(added)
    db.flush()
    survivors: list[Show] = []
    for show in shows:
        kept = folded.get(show.id, show)
        if kept not in survivors:
            survivors.append(kept)
    return survivors, list(folded)


def _keep_edition_details(copy: Show, show: Show) -> None:
    """Give `show` what its unlisted `copy` has from the old formatted edition and it doesn't: a ticket link, a
    benefit's cause, a special event. The page never says these, and the edition is gone."""
    if copy.ticket_url and not show.ticket_url:
        show.ticket_url, show.ticket_provider = copy.ticket_url, copy.ticket_provider
    for field in ("benefit_cause", "special_event"):
        if getattr(copy, field) and not getattr(show, field):
            setattr(show, field, getattr(copy, field))
    show.is_benefit = show.is_benefit or copy.is_benefit
