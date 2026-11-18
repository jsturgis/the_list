"""An event's page on any site, for a Show the List doesn't have yet (the Admin page's links, `add-event`).

A TicketWeb page is read by app/ingestion/ticketweb.py. Any other site's page is read the same way, from the
schema.org Event it describes itself with (its JSON-LD), which most ticketing and venue sites publish: `source`
"page", and the site's name as the ticket provider. A page that can't be fetched (many sites turn scripted requests
away) or has no event details raises UnreadablePage (pages are fetched by app/ingestion/page_fetch.py): a screenshot of the event is the way to add it.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from app.ingestion import ticketweb
from app.ingestion.page_fetch import PageError, get_page
from app.ingestion.ticketweb import EventError, UnreadablePage, event_show, event_url, is_ticketweb_url

SOURCE = "page"

__all__ = ["EventError", "UnreadablePage", "fetch_event", "site_name"]


def site_name(url: str) -> str:
    """The site, as the Show's ticket provider: "eventbrite.com"."""
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def fetch_event(url: str) -> dict:
    """The Show on this event page, as a dict for `ingest_shows`."""
    if is_ticketweb_url(url):
        return ticketweb.fetch_event(url)
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
        raise EventError(f"{url} isn't a web page")
    try:
        html, final_url = get_page(url)
    except PageError as exc:
        raise UnreadablePage(f"couldn't fetch {url}: {exc}") from exc
    return event_show(html, event_url(final_url), source=SOURCE, provider=site_name(url))
