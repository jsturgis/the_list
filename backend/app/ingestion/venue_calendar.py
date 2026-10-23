"""Match a Venue's own calendar against this run's Shows, and work out what Steve's edition didn't have: a flyer,
a link to the Show's own page on the Venue's site ("more info"), and (when the edition has none) a ticket link.
Steve's own data always wins -- this only ever fills a gap, never overwrites one.

match_calendar takes no network or LLM calls, only plain data, so it's tested without either. Everything around it
is a thin IO wrapper:

- find_calendar_url asks the LLM which link on a Venue's homepage is most likely its own calendar/events page, then
  verifies it resolves -- the same "ask for a candidate, then verify" shape as app.pipeline.enrichment's
  _find_soundcloud_url / _find_bandcamp_url.
- fetch_calendar_entries asks the LLM to read the calendar page itself, the same with_structured_output shape as
  app.pipeline.enrichment's _extract_genres_via_llm. Unlike that module's _scrape_text (which strips every tag,
  and every href/src with it), this only strips script/style/comment blocks, so links and image URLs survive.
- enrich_shows_from_venue_calendars ties the two together for one ingestion run: for each Venue among this run's
  Shows, finds (or reuses, or applies a correction for -- app/ingestion/venue_corrections.py) its calendar, reads
  it only when some of this run's Shows still have a gap, and applies match_calendar's updates. A Venue is asked
  at most once (Venue.calendar_checked_at), and one Venue's failure (page down, LLM error) is logged and skipped --
  never worth failing the run over.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel

from app.ingestion.upsert import band_key
from app.ingestion.venue_corrections import venue_correction
from app.pipeline.providers import get_enrichment_llm

logger = logging.getLogger(__name__)

_USER_AGENT = "the-list/0.1 (https://github.com/jsturgis/the_list)"
_HTML_BUDGET = 12000  # characters of cleaned HTML sent to the LLM per calendar page
_STRIP_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


@dataclass(frozen=True)
class CalendarEntry:
    """One Show as a Venue's own calendar page lists it; any field it couldn't find is None."""
    date: date | None = None
    title: str | None = None
    flyer_url: str | None = None
    more_info_url: str | None = None
    ticket_url: str | None = None


@dataclass(frozen=True)
class ShowLike:
    """The only fields match_calendar needs from a Show, so it's tested without a database."""
    id: int
    date: date
    headliner: str
    has_flyer: bool
    has_more_info: bool
    has_ticket: bool


@dataclass(frozen=True)
class CalendarUpdate:
    """The fields a Show should gain from a matched entry -- only ever fields it doesn't already have."""
    flyer_image_url: str | None = None
    more_info_url: str | None = None
    ticket_url: str | None = None

    def is_empty(self) -> bool:
        return not (self.flyer_image_url or self.more_info_url or self.ticket_url)


def _match_one(candidates: list[ShowLike], entry: CalendarEntry) -> ShowLike | None:
    """The one Show among `candidates` (all on the entry's date) the entry belongs to, or None.

    A single Show that night is the match outright -- a Venue rarely doubles up. More than one (an early/late
    pair) is disambiguated by fuzzy-matching the entry's title against each Show's headliner, the same name
    normalization app.ingestion.upsert uses to recognise a Band under another spelling; anything less than exactly
    one match (no title, no match, more than one) is never guessed at.
    """
    if len(candidates) == 1:
        return candidates[0]
    if not entry.title:
        return None
    key = band_key(entry.title)
    matches = [show for show in candidates if band_key(show.headliner) == key]
    return matches[0] if len(matches) == 1 else None


def match_calendar(shows: list[ShowLike], entries: list[CalendarEntry]) -> dict[int, CalendarUpdate]:
    """Which entry belongs to which Show, and what it still needs."""
    by_date: dict[date, list[ShowLike]] = {}
    for show in shows:
        by_date.setdefault(show.date, []).append(show)

    updates: dict[int, CalendarUpdate] = {}
    for entry in entries:
        candidates = by_date.get(entry.date, [])
        show = _match_one(candidates, entry)
        if show is None:
            continue
        update = CalendarUpdate(
            flyer_image_url=None if show.has_flyer else entry.flyer_url,
            more_info_url=None if show.has_more_info else entry.more_info_url,
            ticket_url=None if show.has_ticket else entry.ticket_url,
        )
        if not update.is_empty():
            updates[show.id] = update
    return updates


# ── Finding and reading the calendar page (IO wrappers; not unit-tested beyond mocked network/LLM calls) ──────────

class _CandidateLink(BaseModel):
    url: str | None


def find_calendar_url(venue_name: str, website_url: str) -> str | None:
    """The Venue's calendar/events page: ask the LLM which link on its homepage looks like one, then verify it
    resolves. None when the page can't be fetched, nothing looks right, or the candidate doesn't resolve."""
    try:
        resp = httpx.get(website_url, timeout=10.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.info("venue calendar: couldn't fetch %s's homepage (%s)", venue_name, website_url)
        return None

    links = sorted(set(_HREF_RE.findall(resp.text)))
    if not links:
        return None

    llm = get_enrichment_llm()
    try:
        result = llm.with_structured_output(_CandidateLink).invoke(
            f"Here are the links found on {venue_name}'s homepage ({website_url}). Which one, if any, is most "
            "likely the venue's own calendar or list of upcoming shows/events (not a ticketing site, not social "
            "media)? Reply with that exact URL (absolute or relative), or null if none look right.\n\n"
            + "\n".join(links[:200])
        )
    except Exception:
        logger.warning("venue calendar: LLM lookup failed for %s", venue_name, exc_info=True)
        return None
    if not result.url:
        return None

    candidate = urljoin(website_url, result.url)
    try:
        head = httpx.head(candidate, timeout=10.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
        return candidate if head.status_code < 400 else None
    except httpx.HTTPError:
        return None


def _clean_html(html: str) -> str:
    """Strip script/style/comment blocks and collapse whitespace, keeping every other tag (and its href/src)
    intact, truncated to the LLM's size budget."""
    stripped = _COMMENT_RE.sub("", _STRIP_RE.sub("", html))
    return re.sub(r"\s+", " ", stripped).strip()[:_HTML_BUDGET]


class _ScrapedEntry(BaseModel):
    date: str | None  # "YYYY-MM-DD"; None when it can't be told
    title: str | None
    flyer_url: str | None
    more_info_url: str | None
    ticket_url: str | None


class _ScrapedCalendar(BaseModel):
    entries: list[_ScrapedEntry]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def fetch_calendar_entries(calendar_url: str) -> list[CalendarEntry]:
    """Every Show the Venue's calendar page lists, each with whatever of date/title/flyer/more-info/ticket link
    the LLM could find. [] on any failure: a bad fetch or a bad response is never worth failing the run over."""
    try:
        resp = httpx.get(calendar_url, timeout=15.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.info("venue calendar: couldn't fetch %s", calendar_url)
        return []

    llm = get_enrichment_llm()
    try:
        result = llm.with_structured_output(_ScrapedCalendar).invoke(
            "The HTML below is a music venue's calendar page. List every show/event on it. For each, give its "
            "date (YYYY-MM-DD), its title (usually the headliner's name), its flyer/poster image URL, the URL of "
            "its own 'more info' or detail page on this site (not the calendar page itself), and its "
            "ticket-buying URL. Use null for anything you can't find.\n\n" + _clean_html(resp.text)
        )
    except Exception:
        logger.warning("venue calendar: LLM extraction failed for %s", calendar_url, exc_info=True)
        return []

    return [
        CalendarEntry(
            date=_parse_date(e.date), title=e.title,
            flyer_url=urljoin(calendar_url, e.flyer_url) if e.flyer_url else None,
            more_info_url=urljoin(calendar_url, e.more_info_url) if e.more_info_url else None,
            ticket_url=urljoin(calendar_url, e.ticket_url) if e.ticket_url else None,
        )
        for e in result.entries
    ]


# ── Tying it together for one ingestion run ─────────────────────────────────────────────────────────────────────

def _needs_calendar_match(show) -> bool:
    return not (show.flyer_image_url and show.more_info_url and show.ticket_url)


def _headliner(show) -> str:
    acts = sorted(show.acts, key=lambda a: a.position)
    return acts[0].band.name if acts else ""


def enrich_shows_from_venue_calendars(shows: list) -> int:
    """For every Venue among `shows` that isn't fully filled in yet, find (or reuse, or apply a correction for)
    its calendar, and fill each Show's gaps from whatever it lists. Steve's own data is never overwritten.
    Returns how many Shows were matched. A failure for one Venue never stops the others."""
    by_venue: dict[int, list] = {}
    for show in shows:
        by_venue.setdefault(show.venue_id, []).append(show)

    matched = 0
    for venue_shows in by_venue.values():
        venue = venue_shows[0].venue
        try:
            if venue.calendar_checked_at is None:
                correction = venue_correction(venue.name)
                if correction is not None:
                    venue.calendar_url = correction.calendar_url
                elif venue.website_url:
                    venue.calendar_url = find_calendar_url(venue.name, venue.website_url)
                venue.calendar_checked_at = datetime.utcnow()

            if not venue.calendar_url:
                continue
            pending = [s for s in venue_shows if _needs_calendar_match(s)]
            if not pending:
                continue

            entries = fetch_calendar_entries(venue.calendar_url)
            if not entries:
                continue
            # Every Show at the Venue this run, not just the pending ones: match_calendar's same-night
            # disambiguation needs the full picture, or a complete early show silently leaves a late show's entry
            # looking like the only candidate for that night (and vice versa).
            show_likes = [
                ShowLike(id=s.id, date=s.date, headliner=_headliner(s), has_flyer=bool(s.flyer_image_url),
                         has_more_info=bool(s.more_info_url), has_ticket=bool(s.ticket_url))
                for s in venue_shows
            ]
            by_id = {s.id: s for s in pending}
            for show_id, update in match_calendar(show_likes, entries).items():
                show = by_id[show_id]
                show.flyer_image_url = update.flyer_image_url or show.flyer_image_url
                show.more_info_url = update.more_info_url or show.more_info_url
                show.ticket_url = update.ticket_url or show.ticket_url
                matched += 1
        except Exception:
            logger.warning("venue calendar: skipped %s", venue.name, exc_info=True)
    return matched
