"""Pipeline jobs: the ingest of Steve's List and daily maintenance (`python -m app.cli ingest`), and the check for
a changed List that decides whether to run them (`python -m app.cli check`)."""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import date, datetime, timedelta
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.clock import local_today
from app.config import settings
from app.database import SessionLocal
from app.ingestion.band_photos import save_band_photos
from app.ingestion.backfill import run_backfill
from app.ingestion.band_corrections import band_correction, corrected
from app.ingestion.band_sources import bandcamp_page, discogs_match, photo_candidates, service_genres
from app.ingestion.bandcamp import BandcampUnavailable, bandcamp_photo
from app.ingestion.genre_filter import GenreFilter
from app.ingestion.discogs import discogs_artist, discogs_genres
from app.ingestion.images import check_image_urls
from app.ingestion.ingest_stats import new_band_stats
from app.ingestion.joint_bands import joint_parts, split_joint_acts, split_joint_name
from app.ingestion.lastfm import lastfm_artists, lastfm_tags
from app.ingestion.service_health import failures
from app.ingestion.links import check_links
from app.ingestion.show_flyers import prune_show_flyers, save_show_flyers
from app.ingestion.steve_list import ListPage, edition_title, fetch_list, list_shows
from app.ingestion.spelling import Candidate, respell
from app.ingestion.upsert import (find_band, find_venue, fold_added_shows, known_region, remove_unlisted_shows,
                                  upsert_shows)
from app.ingestion.venue_calendar import enrich_shows_from_venue_calendars
from app.ingestion.venue_check import CONFIRMED, NOT_CHECKED, check_venue, checked_details
from app.ingestion.venue_photos import save_venue_photos
from app.ingestion.wikimedia import commons_photo
from app.models.act import Act
from app.models.band import Band
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.models.show import Show, ShowStatus
from app.models.venue import Venue
from app.embeddings.indexer import SHOW_INDEX_PATH, remove_from_index
from app.pipeline.embed import batch_embed_and_index
from app.pipeline.enrichment import _clean_venue_name, _enrich_band, _enrich_venue


_BAND_LINK_FIELDS = ("spotify_url", "soundcloud_url", "bandcamp_url", "website_url")


def _unsaved_links(db: Session, shows_data: list[dict]) -> set[str]:
    """Links for fields the database doesn't have yet: the only ones upsert would save."""
    links: set[str] = set()
    for data in shows_data:
        if data.get("venue_website"):
            venue = find_venue(db, data["venue_name"], None, (data["city"],)) if data["venue_name"] else None
            if not (venue and venue.website_url):
                links.add(data["venue_website"])
        for name, enrichment in data["band_enrichment"]:
            band = None
            for field in _BAND_LINK_FIELDS:
                if not enrichment.get(field):
                    continue
                band = band or db.query(Band).filter(Band.name == name).first()
                if not (band and getattr(band, field)):
                    links.add(enrichment[field])
    return links


def _apply_venue_data(data: dict, venue_data: dict) -> None:
    """Merge Google Places results into a listing's show dict. Google's address wins (it's complete; the
    listing has at most a street)."""
    data["address"] = venue_data.get("address") or data["address"]
    data["venue_website"] = data["venue_website"] or venue_data.get("website_url")
    for key, source in [
        ("latitude", "latitude"), ("longitude", "longitude"), ("google_place_id", "google_place_id"),
        ("phone", "phone"), ("google_rating", "google_rating"), ("timezone", "timezone"),
        ("venue_description", "description"), ("venue_wikipedia_url", "wikipedia_url"), ("place_city", "city"),
    ]:
        if venue_data.get(source) is not None or key not in data:
            data[key] = venue_data.get(source)


def _last_ingested(db: Session) -> IngestionRun | None:
    """The most recent successful ingestion run."""
    return (db.query(IngestionRun).filter(IngestionRun.status == IngestionStatus.success)
            .order_by(IngestionRun.id.desc()).first())


def _edition_week(day: date) -> date:
    """The Friday on or before `day`: the edition whose week (Friday to Thursday) it's in."""
    return day - timedelta(days=(day.weekday() - 4) % 7)


def list_status(db: Session, page: ListPage) -> dict[str, bool]:
    """How `page` (the List as it is now) compares with what's been ingested.

    `changed`: it isn't the page the last successful run ingested, so there's something to ingest.
    `new_edition`: its date is in a later week (Friday to Thursday) than any edition ingested, so it's the week's
    new edition (Alerts go out), not a correction to the current one. Steve dates the page the day he updates it
    (a Monday's correction says that Monday), so a later date alone isn't a new edition.
    """
    last = _last_ingested(db)
    newest = db.query(func.max(IngestionRun.edition_date)).filter(
        IngestionRun.status == IngestionStatus.success).scalar()
    return {
        "changed": last is None or last.source_hash != page.sha256,
        "new_edition": newest is None or _edition_week(page.edition_date) > _edition_week(newest),
    }


def _newest_edition_runs(db: Session) -> list[IngestionRun]:
    """The successful runs of the newest edition ingested (its week, Friday to Thursday), newest first."""
    newest = db.query(func.max(IngestionRun.edition_date)).filter(
        IngestionRun.status == IngestionStatus.success).scalar()
    if newest is None:
        return []
    runs = (db.query(IngestionRun)
            .filter(IngestionRun.status == IngestionStatus.success, IngestionRun.edition_date.isnot(None))
            .order_by(IngestionRun.id.desc()).all())
    return [r for r in runs if _edition_week(r.edition_date) == _edition_week(newest)]


def alerts_due(db: Session, today: Optional[date] = None) -> bool:
    """Whether the newest edition ingested hasn't had its Alerts yet: the run that ingested it couldn't send them (its
    deploy or the sends failed). Only while it's still that edition's week: a week-old edition's Alerts aren't sent."""
    runs = _newest_edition_runs(db)
    if not runs:
        return False
    week = _edition_week(runs[0].edition_date)
    if (today or local_today()) - week > timedelta(days=6):
        return False
    return not any(r.alerts_sent_at for r in runs)


def mark_alerts_sent(db: Session) -> Optional[IngestionRun]:
    """Record that the newest edition's Alerts went out (on its newest run); the run, or None with no edition."""
    runs = _newest_edition_runs(db)
    if not runs:
        return None
    runs[0].alerts_sent_at = datetime.utcnow()
    db.commit()
    return runs[0]


PhaseReporter = Callable[[str, Optional[str]], None]


def _reporter(on_phase: Optional[PhaseReporter]) -> PhaseReporter:
    """`on_phase`, made safe to call: telling someone how far the ingest has got never fails the ingest."""
    def report(phase: str, detail: Optional[str] = None) -> None:
        if on_phase is None:
            return
        try:
            on_phase(phase, detail)
        except Exception:
            logger.warning("ingestion: couldn't report phase %s", phase, exc_info=True)
    return report


def _respell(name: str):
    """The Band's name spelt right, when it's misspelt and MusicBrainz or Discogs has it spelt right
    (app/ingestion/spelling.py): close names from Last.fm's search, the most listened to looked up as a Band is."""
    def candidates(listed: str) -> list[Candidate]:
        return [Candidate(n, listeners) for n, listeners in lastfm_artists(listed)]
    return respell(name, candidates, lambda n: _enrich_band(n, False),
                   lambda n, found: discogs_match(n, found, discogs_artist))


async def ingest_shows(db: Session, shows_data: list[dict], run: Optional[IngestionRun] = None,
                       source_hash: Optional[str] = None, on_phase: Optional[PhaseReporter] = None) -> list[Show]:
    """Store Shows read from a source (the List, an event page from app/ingestion/ticketweb.py, or a screenshot
    from app/ingestion/screenshot.py): enrich the new Venues and Bands, upsert, save the Band photos, embed. Each
    dict is shaped as `upsert_shows` takes it.

    With `run`, its counts are recorded on it, and `source_hash` once the Shows are stored (the hourly check's mark
    that the List was ingested); without, as for one event added by hand, no ingestion run is kept.

    `on_phase(phase, detail)` is told as each step starts ("venue", "bands", "photos", "saving", "embedding"), for
    an ingest job's progress on the Admin page (app/ingest_jobs.py). A failure to report is logged, never raised.
    """
    report = _reporter(on_phase)
    # Only Venues we haven't seen need Google Places.
    loop = asyncio.get_event_loop()
    report("venue", ", ".join(dict.fromkeys(d["venue_name"] for d in shows_data if d["venue_name"])) or None)
    venue_cache: dict[tuple, dict] = {}
    for data in shows_data:
        name, city = data["venue_name"], data["city"]
        if not name or find_venue(db, name, None, (city,)):
            continue
        street = data["address"].rsplit(",", 1)[0] if data["address"] else None
        key = (name, city, street)
        if key not in venue_cache:
            logger.info("ingestion: enriching new venue %s (%s)", name, city)
            report("venue", f"Looking up {name} on Google Places")
            # No LLM calls at ingest: the name is searched as Steve lists it, and there's no Wikipedia description.
            found = await loop.run_in_executor(None, _enrich_venue, name, city or "", street, False)
            # Google's best guess is kept only as far as it's the listed Venue (app/ingestion/venue_check.py).
            check = check_venue(name, city, street, found)
            if check.status not in (CONFIRMED, NOT_CHECKED):
                logger.warning("ingestion: new venue %s (%s) not confirmed on Google Places (%s): %s",
                               name, city, check.status, check.reason)
            venue_cache[key] = checked_details(found, check)
        _apply_venue_data(data, venue_cache[key])

    # New names that are two Bands billed together ("Dying Fetus And Sanguisugabogg") become two Acts; real
    # Bands with "and" in the name ("Belle and Sebastian") don't. MusicBrainz decides, once per name.
    split_cache: dict[str, list[str]] = {}

    def split(name: str) -> list[str]:
        if name not in split_cache:
            known = joint_parts(name) is None or find_band(db, name)
            split_cache[name] = [name] if known else split_joint_name(name)
        return split_cache[name]

    for data in shows_data:
        for name, halves in await loop.run_in_executor(None, split_joint_acts, data, split):
            logger.info("ingestion: %r is a joint billing: %s", name, " + ".join(halves))
        # A Band's correction (app/ingestion/band_corrections) gives the genres and links to use when the services
        # have none.
        data["band_enrichment"] = [(name, corrected(name, e)) for name, e in data["band_enrichment"]]

    # New Bands: look them up on MusicBrainz (no LLM), once per name. The List only names a Band; the services
    # are the source of everything else. Genres: MusicBrainz's curated genres, else Last.fm's tags, else
    # Discogs' genres and styles, else MusicBrainz's free-form tags, else its correction's.
    # Links: each one MusicBrainz has, else its correction's.
    # A Band already in the database (under any spelling, see find_band) was looked up when it was new, so it isn't
    # tried again.
    band_cache: dict[str, dict | None] = {}
    renamed: dict[str, str] = {}   # a listed name a service spells otherwise: "Sunamo" -> "Sunami"
    genre_cache: dict[str, list[str]] = {}  # each new Band's genres from the services, asked once
    # New Bands whose lookup met a service that was down (app/ingestion/service_health.py): saved with what the
    # others had, but not marked looked up, so they're looked up again (retry_pending_bands).
    unavailable: set[str] = set()
    # Keeps only genres. If the genre model is down, unknown tags are kept this run rather than lost for good.
    genre_filter = GenreFilter.load(db, keep_unknown=True)
    report("bands", None)
    for data in shows_data:
        for i, (name, enrichment) in enumerate(data["band_enrichment"]):
            if name not in band_cache:
                known = find_band(db, name)
                if known and name in known.spellings:
                    renamed[name] = known.name   # listed misspelt before, and put right then
                    band_cache[name] = None
                elif known:
                    band_cache[name] = None
                else:
                    before = failures()
                    logger.info("ingestion: looking up genres for %s", name)
                    report("bands", f"Looking up Band {i + 1} of {len(data['band_enrichment'])}: {name}")
                    found = await loop.run_in_executor(None, _enrich_band, name, False)
                    # Its photo on Wikimedia Commons, through MusicBrainz's Wikidata link, with its credit.
                    photo = await loop.run_in_executor(None, commons_photo, found.get("links") or [])
                    # Its Discogs artist (members, photo, page), through MusicBrainz's Discogs link or its name.
                    artist = await loop.run_in_executor(None, discogs_match, name, found, discogs_artist)
                    # No service has the name: it may be misspelt. A close name a service has is the Band's
                    # (app/ingestion/spelling.py); without one, the name stays as listed.
                    if not found.get("mbid") and artist is None and not found.get("namesakes"):
                        report("bands", f"Checking the spelling of {name}")
                        fixed = await loop.run_in_executor(None, _respell, name)
                        if fixed:
                            renamed[name] = fixed.name
                            found, artist = fixed.found, fixed.discogs
                    # Its Bandcamp band photo, only when neither has a photo. Bandcamp often won't serve a page
                    # right away; the Band then has no photo for now (backfill --recheck-photos tries again).
                    bandcamp = None
                    correction = band_correction(name)
                    page = bandcamp_page(found, found.get("bandcamp_url") or enrichment.get("bandcamp_url"),
                                         correction.links.get("bandcamp_url") if correction else None)
                    if page and not photo and not (artist and artist.image_url):
                        try:
                            bandcamp = await loop.run_in_executor(None, bandcamp_photo, page)
                        except BandcampUnavailable as exc:
                            logger.info("ingestion: no Bandcamp photo for %s for now: %s", name, exc)
                    band_cache[name] = {**found, "commons_photo": photo, "discogs": artist, "bandcamp_photo": bandcamp}
                    if failures() - before:
                        unavailable.add(name)
            found = band_cache[name]
            if found:
                links = {k: v for k, v in found.items() if k.endswith("_url") and v}
                links["mb_links"] = found.get("links") or []  # every MusicBrainz link, for app/band_links.py
                # Photos, in order (app/ingestion/band_sources): Commons, Discogs, Bandcamp.
                # The first that loads is used; the rest are fallbacks if it turns out to be gone when downloaded.
                artist = found.get("discogs")
                candidates = photo_candidates(found.get("commons_photo"), artist, found.get("bandcamp_photo"))
                if candidates:
                    links.update(image_url=candidates[0]["url"], image_credit=candidates[0]["credit"],
                                 image_candidates=candidates)
                # Genres from the services in order (app/ingestion/band_sources), asked once per name; only when
                # every service has none, its correction's.
                if name not in genre_cache:
                    before = failures()
                    genre_cache[name] = await loop.run_in_executor(
                        None, service_genres, renamed.get(name, name), found, lastfm_tags, discogs_genres,
                        genre_filter.keep)
                    if failures() - before:
                        unavailable.add(name)
                genres = genre_cache[name] or await loop.run_in_executor(
                    None, genre_filter.keep, enrichment["genres"])
                # Its Discogs members are saved with the Band.
                data["band_enrichment"][i] = (name, {**enrichment, **links, "genres": genres, "discogs": artist,
                                                     "members": artist.members if artist else []})

    # Photo URLs from the services are sometimes broken: keep (or repair) only those that load.
    image_urls = [d["venue_image_url"] for d in shows_data if d.get("venue_image_url")] + [
        url for d in shows_data for _, e in d["band_enrichment"]
        for url in ([c["url"] for c in e["image_candidates"]] if e.get("image_candidates") else [e.get("image_url")])
        if url]
    if image_urls:
        report("photos", f"Checking {len(image_urls)} photo{'s' if len(image_urls) != 1 else ''}")
        checked = await loop.run_in_executor(None, check_image_urls, image_urls)
        for data in shows_data:
            if data.get("venue_image_url"):
                data["venue_image_url"] = checked.get(data["venue_image_url"])
            for _, enrichment in data["band_enrichment"]:
                if candidates := enrichment.get("image_candidates"):
                    # The first candidate that loads (repaired if need be); the rest stay as fallbacks.
                    loading = [{**c, "url": checked[c["url"]]} for c in candidates if checked.get(c["url"])]
                    first = loading[0] if loading else {"url": None, "credit": None}
                    enrichment.update(image_url=first["url"], image_credit=first["credit"],
                                      image_fallbacks=loading[1:])
                elif enrichment.get("image_url"):
                    enrichment["image_url"] = checked.get(enrichment["image_url"])

    # Skip links that don't work: domains that don't exist, missing pages (Bandcamp links aren't checked).
    links = _unsaved_links(db, shows_data)
    if links:
        works = await loop.run_in_executor(None, check_links, sorted(links))
        broken = {url for url, ok in works.items() if not ok}
        for data in shows_data:
            if data.get("venue_website") in broken:
                data["venue_website"] = None
            for _, enrichment in data["band_enrichment"]:
                for field in _BAND_LINK_FIELDS:
                    if enrichment.get(field) in broken:
                        enrichment[field] = None

    report("saving", None)
    shows_before, venues_before = db.query(Show).count(), db.query(Venue).count()
    if renamed:
        # Stored under the right spelling; the listed one is kept on the Band, for the next listing that uses it.
        for data in shows_data:
            data["bands"] = [renamed.get(b, b) for b in data["bands"]]
            data["band_enrichment"] = [(renamed.get(n, n), e) for n, e in data["band_enrichment"]]
    shows = upsert_shows(db, shows_data)
    for listed, fixed in renamed.items():
        band = find_band(db, fixed)
        if band and listed not in band.spellings:
            band.spellings = [*band.spellings, listed]
            logger.info("ingestion: %r is listed as %r; spelt as the services have it", fixed, listed)
    # One event added from elsewhere and listed by Steve, spelled differently, is one Show: the List's.
    shows, folded = fold_added_shows(db, shows)
    shows_new, new_venues = db.query(Show).count() - shows_before, db.query(Venue).count() - venues_before
    if run:
        run.shows_upserted, run.shows_new, run.new_venues = len(shows), shows_new, new_venues
        # Recorded once the page's Shows are in: a run that fails before this is tried again at the next check.
        run.source_hash = source_hash
    genre_filter.save(db)  # the tags judged this run, kept for next time
    db.commit()
    logger.info("ingestion: upserted %d shows (%d new); %d new venues", len(shows), shows_new, new_venues)
    if folded:
        remove_from_index(SHOW_INDEX_PATH, folded)
        logger.info("ingestion: folded %d shows from elsewhere into the List's: %s", len(folded), folded)

    # Reload with relationships for embedding
    show_ids = [s.id for s in shows]
    shows = (
        db.query(Show)
        .options(joinedload(Show.venue), joinedload(Show.acts).joinedload(Act.band))
        .filter(Show.id.in_(show_ids))
        .all()
    )

    # Photos are kept with the data: download each Band's that's still a remote URL into the images folder.
    bands = list({a.band.id: a.band for s in shows for a in s.acts}.values())
    # The photos after each new Band's chosen one, in case that one turns out to be gone (first Show wins).
    fallbacks: dict[str, list[dict]] = {}
    for d in shows_data:
        for name, e in d["band_enrichment"]:
            if e.get("image_fallbacks"):
                fallbacks.setdefault(name, e["image_fallbacks"])
    stored = await loop.run_in_executor(None, save_band_photos, bands, settings.images_path, fallbacks)
    db.commit()
    if stored:
        logger.info("ingestion: saved %d band photos", stored)
    # And each Venue's that's still a remote URL (the site shows none until it's stored).
    venues = list({s.venue.id: s.venue for s in shows}.values())
    stored = await loop.run_in_executor(None, save_venue_photos, venues, settings.images_path)
    db.commit()
    if stored:
        logger.info("ingestion: saved %d venue photos", stored)

    # How the new Bands came out: how many, and the share no service had a photo for.
    # Under the name they're stored by: a misspelt listing's is the services' spelling.
    new_names = {renamed.get(name, name) for name, found in band_cache.items() if found is not None}
    down = {renamed.get(name, name) for name in unavailable}
    looked_up_at = datetime.utcnow()
    for band in bands:
        if band.name in new_names and band.name not in down:
            band.enriched_at = looked_up_at
    if down:
        logger.warning("ingestion: a service was down while looking up %d new bands; they'll be looked up again: %s",
                       len(down), ", ".join(sorted(down)))
    band_stats = new_band_stats([b for b in bands if b.name in new_names])
    if run:
        for field, value in band_stats.items():
            setattr(run, field, value)
    db.commit()
    logger.info("ingestion: %s new bands; %s%% without a photo", band_stats["new_bands"],
                band_stats["new_bands_without_photo_pct"])

    # Each Show's own Venue calendar, when it has one: a flyer, a more-info link, and (when the List has none) a
    # ticket link. Never overwrites what the List gave the Show. Never worth failing the ingest over.
    try:
        matched = await loop.run_in_executor(None, enrich_shows_from_venue_calendars, shows)
        stored_flyers = await loop.run_in_executor(None, save_show_flyers, shows, settings.images_path)
        pruned = prune_show_flyers(db, settings.images_path, local_today())
        db.commit()
        logger.info("ingestion: matched %d shows against their venue's calendar; saved %d flyers, deleted %d",
                    matched, stored_flyers, pruned)
    except Exception:
        db.rollback()
        logger.warning("ingestion: venue calendars skipped this run", exc_info=True)

    # Embeddings are only for Similar Bands (and the local similarShows query): never worth failing the ingest over,
    # when the Shows are already stored. What wasn't embedded is embedded at the next run (app/pipeline/embed.py).
    logger.info("ingestion: embedding and indexing")
    report("embedding", None)
    try:
        await batch_embed_and_index(db, shows)
        db.commit()   # the embeddings
    except Exception:
        db.rollback()
        logger.warning("ingestion: embedding skipped this run", exc_info=True)
    return shows


_RETRY_BANDS = 10
_RETRY_MINUTES = 3


async def retry_pending_bands(db: Session, created_before: datetime) -> None:
    """Look up again, as the backfill does, a few Bands left not looked up (enriched_at) by an earlier run that met a
    service that was down, so they don't wait for someone to run the Backfill workflow. Only Bands from before this
    run: the ones it just left are likely to meet the same outage. Never fails the ingest."""
    try:
        result = await run_backfill(db, settings.images_path, max_minutes=_RETRY_MINUTES, limit=_RETRY_BANDS,
                                    created_before=created_before)
        if result["looked_up"] or result["failed"]:
            logger.info("ingestion: looked up %d bands again (%d failed)", result["looked_up"], result["failed"])
    except Exception:
        db.rollback()
        logger.warning("ingestion: bands left to look up again skipped this run", exc_info=True)


async def _run_ingestion_async(db: Optional[Session] = None) -> None:
    """Full pipeline: fetch the List → parse → enrich new Venues and Bands → upsert → embed."""
    _own_db = db is None
    if _own_db:
        db = SessionLocal()

    run = IngestionRun(started_at=datetime.utcnow(), status=IngestionStatus.success)
    db.add(run)
    db.flush()
    outages_before = failures()

    try:
        logger.info("ingestion: fetching the List from %s", settings.list_url)
        the_list = fetch_list()
        run.edition_date = the_list.edition_date
        run.edition_title = edition_title(the_list.edition_date)
        shows_data = list_shows(the_list.text)
        run.shows_parsed = len(shows_data)
        logger.info("ingestion: %d shows in %s", len(shows_data), run.edition_title)

        shows = await ingest_shows(db, shows_data, run, source_hash=the_list.sha256)
        # The page lists every upcoming Show: the stored ones it no longer does are gone from the List.
        removed = remove_unlisted_shows(db, shows, min(data["date"] for data in shows_data))

        await retry_pending_bands(db, created_before=run.started_at)
        outages = failures() - outages_before
        if outages:
            logger.warning("ingestion: services that didn't answer this run: %s",
                           ", ".join(f"{service} ({count})" for service, count in sorted(outages.items())))

        run.finished_at = datetime.utcnow()
        db.commit()
        if removed:
            remove_from_index(SHOW_INDEX_PATH, removed)
            logger.info("ingestion: removed %d shows no longer on the List: %s", len(removed), removed)
        logger.info("ingestion: done")

    except Exception as exc:
        logger.exception("ingestion: pipeline failed")
        run.status = IngestionStatus.failure
        run.error = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-2000:]
        run.finished_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        if _own_db:
            db.close()


async def _run_venue_enrichment_async(venue_id: Optional[int] = None) -> None:
    """Re-enrich one venue (by id) or all venues, overwriting existing data."""
    db = SessionLocal()
    try:
        # Clear caches so stale data isn't returned
        _enrich_venue.cache_clear()
        _clean_venue_name.cache_clear()

        venues = (
            db.query(Venue).filter(Venue.id == venue_id).all()
            if venue_id
            else db.query(Venue).all()
        )
        logger.info("venue enrichment: refreshing %d venue(s)", len(venues))

        loop = asyncio.get_event_loop()
        for venue in venues:
            logger.info("venue enrichment: enriching %s", venue.name)
            found = await loop.run_in_executor(None, _enrich_venue, venue.name, venue.city or "")
            # Only what Google has for this very Venue overwrites what's stored (app/ingestion/venue_check.py).
            check = check_venue(venue.name, venue.city, None, found)
            if check.status not in (CONFIRMED, NOT_CHECKED):
                logger.warning("venue enrichment: %s not confirmed on Google Places (%s): %s",
                               venue.name, check.status, check.reason)
            data = checked_details(found, check)
            if not data:
                continue
            for attr, key in [
                ("website_url", "website_url"),
                ("address", "address"),
                ("google_place_id", "google_place_id"),
                ("timezone", "timezone"),
                ("phone", "phone"),
                ("description", "description"),
                ("wikipedia_url", "wikipedia_url"),
            ]:
                if data.get(key) is not None:
                    setattr(venue, attr, data[key])
            for attr in ("latitude", "longitude", "google_rating"):
                if data.get(attr) is not None:
                    setattr(venue, attr, data[attr])
            if data.get("city"):
                venue.city = data["city"]
                # Only move Regions for a known city; Google can return a neighbourhood.
                venue.region = known_region(data["city"]) or venue.region

        db.commit()
        logger.info("venue enrichment: done")
    except Exception:
        logger.exception("venue enrichment: failed")
        db.rollback()
        raise
    finally:
        db.close()


def run_daily_maintenance(db: Optional[Session] = None) -> None:
    """Mark past shows and hard-delete shows older than DATA_RETENTION_DAYS."""
    _own_db = db is None
    if _own_db:
        db = SessionLocal()
    try:
        today = local_today()
        cutoff = today - timedelta(days=settings.data_retention_days)

        db.query(Show).filter(
            Show.date < today,
            Show.status == ShowStatus.upcoming,
        ).update({Show.status: ShowStatus.past})

        for show in db.query(Show).filter(Show.date < cutoff).all():
            db.delete(show)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if _own_db:
            db.close()
