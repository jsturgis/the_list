"""An event's page on any site, for a Show the List doesn't have yet (the Admin page's links, `add-event`).

A TicketWeb page is read by app/ingestion/ticketweb.py. Any other site's page is read the same way, from the
schema.org Event it describes itself with (its JSON-LD), which most ticketing and venue sites publish: `source`
"page", and the site's name as the ticket provider. A page listing several events (an artist's page) gives a Show for
each in the Bay Area. A page that can't be fetched (many sites turn scripted requests away; pages are fetched by
app/ingestion/page_fetch.py) or has no event details raises UnreadablePage: a screenshot of the event is the way to
add it.

A page often knows less than the site that sells the tickets, so more is read where the page points:
- A Bandsintown event page's whole lineup, which its JSON-LD leaves at the headliner (app/ingestion/bandsintown.py).
- On a page of several events, each Show's own event page (its lineup and ticket link), for the first
  MAX_FOLLOWED Shows.
- The ticket seller's page (`follow_seller`): the event's ticket link on another site, unwrapped from an affiliate
  redirect. Its event, on the same date, adds the Bands the page didn't name, fills in what the page left out (price,
  times, age) and has the last word on sold out and cancelled; the Show's ticket link becomes the seller's. A seller
  whose page can't be read (Ticketmaster's asks a browser to prove itself) still gives the Show its ticket link. Any
  of this failing leaves the Show as the page gave it.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlsplit

from app.ingestion import bandsintown, ticketweb
from app.ingestion.page_fetch import PageError, get_page
from app.ingestion.ticketweb import (EventError, OutsideBayArea, UnreadablePage, event_shows, event_url,
                                     is_ticketweb_url)

logger = logging.getLogger(__name__)

SOURCE = "page"
# How many of a page's Shows get their own event page and ticket seller's page fetched: each is a request or two.
MAX_FOLLOWED = 5
# An affiliate redirect's parameter holding where it goes: Impact's (ticketmaster.evyy.net/c/...?u=), and others'.
_REDIRECT_PARAMS = ("u", "url", "murl", "destination", "redirect")
# Filled in from the seller's page when the page left them out.
_FILLED = ("price_raw", "age_restriction", "address", "venue_website")

__all__ = ["EventError", "OutsideBayArea", "UnreadablePage", "fetch_events", "site_name"]


def site_name(url: str) -> str:
    """The site, as the Show's ticket provider: "eventbrite.com"."""
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def fetch_events(url: str) -> list[dict]:
    """The Shows on this page, as dicts for `ingest_shows`: its event, or its events in the Bay Area."""
    if is_ticketweb_url(url):
        return [_finish(ticketweb.fetch_event(url))]
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
        raise EventError(f"{url} isn't a web page")
    html, final_url = _get(url)
    shows = event_shows(html, event_url(final_url), source=SOURCE, provider=site_name(url))
    if len(shows) == 1:
        shows = [_with_page_details(shows[0], html, final_url)]
    else:
        shows = [_from_own_page(show, final_url) if n < MAX_FOLLOWED else show for n, show in enumerate(shows)]
    return [_finish(follow_seller(show) if n < MAX_FOLLOWED else show) for n, show in enumerate(shows)]


def _get(url: str) -> tuple[str, str]:
    try:
        return get_page(url)
    except PageError as exc:
        raise UnreadablePage(f"couldn't fetch {url}: {exc}") from exc


def _finish(show: dict) -> dict:
    show.pop("offer_urls", None)
    show.pop("lineup_named", None)
    return show


def _with_page_details(show: dict, html: str, page_url: str) -> dict:
    """What the page says beyond its JSON-LD: a Bandsintown event's whole lineup, and its seller's link."""
    if not bandsintown.is_bandsintown_url(page_url):
        return show
    lineup = bandsintown.lineup(html)
    if len(lineup) > len(show["bands"]):
        show = _with_bands(show, _merged(show["bands"], lineup))
    return {**show, "offer_urls": bandsintown.seller_urls(html) + show.get("offer_urls", [])}


def _from_own_page(show: dict, page_url: str) -> dict:
    """A Show from a page of several events, with what its own event page adds (the same event: its date and
    Venue), or as it was if that page can't be read."""
    own = show["ticket_url"]
    if site_name(own) != site_name(page_url) or event_url(own) == event_url(page_url):
        return show
    try:
        html, final_url = get_page(own)
        found = [s for s in event_shows(html, event_url(final_url), source=show["source"],
                                        provider=show["ticket_provider"])
                 if s["date"] == show["date"] and s["venue_name"] == show["venue_name"]]
    except (PageError, EventError) as exc:
        logger.info("%s: its own page adds nothing: %s", own, exc)
        return show
    if not found:
        return show
    return _with_page_details({**show, **found[0], "ticket_url": show["ticket_url"]}, html, final_url)


def seller_url(show: dict) -> str | None:
    """The ticket seller's page for the Show: its first ticket link on another site, unwrapped from an affiliate
    redirect."""
    for link in show.get("offer_urls", []):
        link = _unwrapped(link)
        if site_name(link) and site_name(link) != site_name(show["ticket_url"]):
            return link
    return None


def _unwrapped(link: str) -> str:
    """Where an affiliate redirect goes ("https://ticketmaster.evyy.net/c/1/2/3?u=https%3A%2F%2Fwww.ticketmaster.com
    %2F..."), else the link itself."""
    for _ in range(3):
        query = parse_qs(urlsplit(link).query)
        target = next((query[key][0] for key in _REDIRECT_PARAMS
                       if key in query and query[key][0].startswith(("http://", "https://"))), None)
        if not target:
            break
        link = target
    return link


def follow_seller(show: dict) -> dict:
    """The Show with what its ticket seller's page adds; the seller's link as its ticket link even when the page
    can't be read."""
    link = seller_url(show)
    if not link:
        return show
    with_link = {**show, "ticket_url": event_url(link), "ticket_provider": _provider(link)}
    try:
        html, final_url = get_page(link)
        if is_ticketweb_url(final_url):
            sold = [ticketweb.event_show(html, event_url(final_url))]
        else:
            sold = event_shows(html, event_url(final_url), source=show["source"], provider=site_name(final_url))
    except (PageError, EventError) as exc:
        logger.info("%s: its seller's page (%s) adds nothing: %s", show["ticket_url"], link, exc)
        return with_link
    same = [s for s in sold if s["date"] == show["date"]]
    if not same:
        logger.info("%s: its seller's page (%s) has no event on %s", show["ticket_url"], link, show["date"])
        return show   # likely another event: not its ticket link either
    return merge_seller(show, same[0])


def _provider(url: str) -> str:
    return ticketweb.PROVIDER if is_ticketweb_url(url) else site_name(url)


def merge_seller(show: dict, seller: dict) -> dict:
    """The page's Show with its seller's event: the seller's Bands after the page's, what the page left out, the
    seller's word on sold out and cancelled, and the seller's ticket link."""
    more = seller["bands"] if seller.get("lineup_named", True) else []
    merged = _with_bands(show, _merged(show["bands"], more))
    for key in _FILLED:
        if not merged.get(key) and seller.get(key):
            merged[key] = seller[key]
    if seller.get("set_time"):   # the seller gave doors and the start: both are better than the page's one time
        merged["door_time"], merged["set_time"] = seller["door_time"], seller["set_time"]
    elif not merged.get("door_time"):
        merged["door_time"] = seller.get("door_time")
    merged["is_sold_out"] = bool(show.get("is_sold_out") or seller.get("is_sold_out"))
    if seller.get("status") and seller["status"] != "upcoming":
        merged["status"] = seller["status"]
    merged["ticket_url"] = seller["ticket_url"]
    merged["ticket_provider"] = seller["ticket_provider"]
    return merged


def _merged(first: list[str], more: list[str]) -> list[str]:
    """`first`, then the names in `more` it doesn't have. A name that contains one it has, or is part of one, is
    taken for the same Band written up ("TEENAGE BOTTLEROCKET Live in Berkeley"), not another."""
    names = list(first)
    for name in more:
        if not any(_within(name, had) or _within(had, name) for had in names):
            names.append(name)
    return names


def _within(part: str, whole: str) -> bool:
    """Whether `part` is `whole`, or whole words of it ("Ex" isn't part of "Exhumed")."""
    return re.search(rf"(?<!\w){re.escape(part.casefold())}(?!\w)", whole.casefold()) is not None


def _with_bands(show: dict, bands: list[str]) -> dict:
    return {**show, "bands": bands, "act_notes": [None] * len(bands),
            "band_enrichment": [(name, {"genres": []}) for name in bands]}
