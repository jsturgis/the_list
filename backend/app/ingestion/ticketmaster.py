"""What a Ticketmaster event page says beyond its schema.org Event (app/ingestion/event_page.py reads that): its price.

Its JSON-LD has no offers, and the page draws its ticket options, prices and all, with scripts after it loads. So its
page is fetched in the page fetcher's browser, waiting for those options (`READY`, sent as the fetch's `wait_for`),
and the price is read from them: each carries it (`data-price="$48.00"`, with Ticketmaster's fees, as California
requires prices to be shown). A sold-out event, or one not on sale yet, has none: no price.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.ingestion.ticketweb import _money_range

# The ticket options ("quick picks"), once the page has drawn them. Checked 2026-11-18.
READY = '[data-bdd^="quick-picks-list-item"][data-price]'
_OPTION_RE = re.compile(r'<[a-z]+\b[^>]*\bdata-bdd="quick-picks-list-item[^"]*"[^>]*>', re.IGNORECASE)
_PRICE_RE = re.compile(r'\bdata-price="\$([\d,]+(?:\.\d+)?)"')


def is_ticketmaster_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host == "ticketmaster.com" or host.endswith(".ticketmaster.com")


def price(page: str) -> str | None:
    """The price as the List writes it ("$48", "$48/$65"), from the ticket options the page drew; None without
    any."""
    amounts = [float(found.group(1).replace(",", ""))
               for option in _OPTION_RE.finditer(page) if (found := _PRICE_RE.search(option.group(0)))]
    return _money_range(min(amounts), max(amounts)) if amounts else None
