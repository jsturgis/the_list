"""The weekly Alerts: each person's Saved Filters run against the Upcoming Shows, one email per person.

People, their Saved Filters and whether their Alerts are on live in Supabase (ADR 0003); this reads them with
the project's secret key. Each Saved Filter stores the Shows list's URL query string, which becomes the same
filters the GraphQL `shows` query takes, so an Alert lists exactly what the site shows for that filter.

Only a dry run exists so far: the emails are printed. Sending comes with #61.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass, field
from typing import TextIO
from urllib.parse import parse_qs

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.graphql.queries import query_shows
from app.graphql.types import ShowFilters
from app.models.show import Show

logger = logging.getLogger(__name__)

# Shows listed per Saved Filter; the rest are behind a "See all" link.
SHOWS_PER_FILTER = 25
_PAGE = 1000
# Params the old Shows list used before the combined band-or-venue search (`q`); see frontend lib/filters.
_LEGACY_SEARCH_PARAMS = ("band", "venue")


class SupabaseError(RuntimeError):
    pass


@dataclass
class SavedFilter:
    name: str
    query: str


@dataclass
class Subscriber:
    email: str
    unsubscribe_token: str
    saved_filters: list[SavedFilter] = field(default_factory=list)


@dataclass
class ShowLine:
    show_id: int
    date_label: str
    headliner: str
    venue: str
    city: str
    url: str


@dataclass
class Section:
    """One Saved Filter's matches in an Alert."""

    name: str
    shows: list[ShowLine]
    total: int
    see_all_url: str


@dataclass
class AlertEmail:
    to: str
    unsubscribe_token: str
    subject: str
    sections: list[Section]
    text: str
    html: str


# ── Supabase ──────────────────────────────────────────────────────────────────

def _get(path: str, params: dict) -> httpx.Response:
    # The secret key (sb_secret_...) goes in `apikey`; it isn't a JWT, so no Authorization header.
    try:
        response = httpx.get(f"{settings.supabase_url.rstrip('/')}{path}", params=params,
                             headers={"apikey": settings.supabase_service_role_key}, timeout=30.0)
        response.raise_for_status()
        return response
    except Exception as exc:
        raise SupabaseError(f"Supabase request to {path} failed: {exc}") from exc


def _rows(table: str, params: dict) -> list[dict]:
    rows: list[dict] = []
    while True:
        page = _get(f"/rest/v1/{table}", {**params, "limit": _PAGE, "offset": len(rows)}).json()
        rows += page
        if len(page) < _PAGE:
            return rows


def _emails_by_user() -> dict[str, str]:
    emails: dict[str, str] = {}
    page = 1
    while True:
        users = _get("/auth/v1/admin/users", {"page": page, "per_page": _PAGE}).json().get("users", [])
        emails.update({u["id"]: u["email"] for u in users if u.get("email")})
        if len(users) < _PAGE:
            return emails
        page += 1


def fetch_subscribers() -> list[Subscriber]:
    """Everyone with Alerts turned on, with their Saved Filters in the order they were saved."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SupabaseError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    subscriptions = _rows("alert_subscriptions", {"select": "user_id,unsubscribe_token", "enabled": "eq.true"})
    saved = _rows("saved_filters", {"select": "user_id,name,query,created_at", "order": "created_at.asc"})
    emails = _emails_by_user()

    by_user = {s["user_id"]: Subscriber(emails[s["user_id"]], s["unsubscribe_token"])
               for s in subscriptions if s["user_id"] in emails}
    for row in saved:
        if row["user_id"] in by_user:
            by_user[row["user_id"]].saved_filters.append(SavedFilter(row["name"], row["query"]))
    return list(by_user.values())


# ── matching ──────────────────────────────────────────────────────────────────

def filters_from_query(query: str) -> ShowFilters:
    """A Saved Filter's query string as the GraphQL `shows` filters; the Python twin of frontend buildFilters."""
    params = {k: v[0].strip() for k, v in parse_qs(query).items() if v and v[0].strip()}
    search = params.get("q") or " ".join(params[k] for k in _LEGACY_SEARCH_PARAMS if k in params)
    price = params.get("priceMax")
    return ShowFilters(
        search=search or None,
        region=params.get("region"),
        from_date=params.get("fromDate"),
        to_date=params.get("toDate"),
        price_max=float(price) if price else None,
        is_free=True if params.get("free") == "1" else None,
        age_restriction=params.get("age"),
        genre=params.get("genre"),
    )


def _matching_shows(db: Session, query: str) -> list[Show]:
    shows = query_shows(db, filters_from_query(query), limit=100_000, offset=0)
    # The site lists a day's Shows by door time (frontend filterShows); unknown door times first.
    return sorted(shows, key=lambda s: (s.date, s.door_time.isoformat() if s.door_time else ""))


def _show_line(show: Show, site: str) -> ShowLine:
    acts = sorted(show.acts, key=lambda a: a.position)
    return ShowLine(
        show_id=show.id,
        date_label=f"{show.date:%a, %b} {show.date.day}",
        headliner=acts[0].band.name if acts else "Unknown",
        venue=show.venue.name,
        city=show.venue.city,
        url=f"{site}/shows/{show.id}/",
    )


# ── emails ────────────────────────────────────────────────────────────────────

def _subject(sections: list[Section]) -> str:
    count = len({line.show_id for s in sections for line in s.shows})
    return f"{count} upcoming {'show' if count == 1 else 'shows'} for your alerts"


def _text(sections: list[Section], site: str) -> str:
    lines = ["Upcoming shows for your alerts on The List", ""]
    for s in sections:
        lines.append(f"{s.name} — {s.total} {'show' if s.total == 1 else 'shows'}")
        for line in s.shows:
            lines += [f"  {line.date_label} · {line.headliner} at {line.venue}, {line.city}", f"    {line.url}"]
        if s.total > len(s.shows):
            lines.append(f"  See all {s.total} on The List: {s.see_all_url}")
        lines.append("")
    lines.append(f"Manage your alerts: {site}/alerts/")
    return "\n".join(lines) + "\n"


def _html(sections: list[Section], site: str) -> str:
    e = html.escape
    parts = ['<div style="font-family: Arial, Helvetica, sans-serif; color: #18181b; max-width: 600px">',
             '<h1 style="font-size: 20px">Upcoming shows for your alerts</h1>']
    for s in sections:
        parts.append(f'<h2 style="font-size: 16px; margin-top: 24px">{e(s.name)} '
                     f'<span style="color: #71717a; font-weight: normal">· {s.total} '
                     f'{"show" if s.total == 1 else "shows"}</span></h2><ul style="padding-left: 18px">')
        for line in s.shows:
            parts.append(f'<li style="margin-bottom: 6px"><a href="{e(line.url)}" style="color: #b45309">'
                         f'{e(line.headliner)}</a> · {e(line.date_label)} · {e(line.venue)}, {e(line.city)}</li>')
        parts.append("</ul>")
        if s.total > len(s.shows):
            parts.append(f'<p><a href="{e(s.see_all_url)}" style="color: #b45309">See all {s.total} on The List</a></p>')
    parts.append(f'<p style="margin-top: 32px; font-size: 12px; color: #71717a">'
                 f'<a href="{e(site)}/alerts/" style="color: #71717a">Manage your alerts</a></p></div>')
    return "".join(parts)


def build_alerts(db: Session, subscribers: list[Subscriber], site: str) -> list[AlertEmail]:
    """One Alert per person whose Saved Filters match any Upcoming Shows; nothing for the rest."""
    emails = []
    cache: dict[str, list[Show]] = {}  # people often save the same filters
    for person in subscribers:
        sections = []
        for saved in person.saved_filters:
            if saved.query not in cache:
                cache[saved.query] = _matching_shows(db, saved.query)
            matches = cache[saved.query]
            if matches:
                sections.append(Section(saved.name, [_show_line(s, site) for s in matches[:SHOWS_PER_FILTER]],
                                        len(matches), f"{site}/?{saved.query}"))
        if sections:
            emails.append(AlertEmail(person.email, person.unsubscribe_token, _subject(sections), sections,
                                     _text(sections, site), _html(sections, site)))
    return emails


def run_alerts(db: Session, *, dry_run: bool, out: TextIO) -> list[AlertEmail]:
    """Build this week's Alerts. A dry run prints them to `out`; sending isn't built yet (#61)."""
    if not dry_run:
        raise NotImplementedError("Sending Alerts isn't available yet; use --dry-run")
    subscribers = fetch_subscribers()
    site = settings.site_url.rstrip("/")
    emails = build_alerts(db, subscribers, site)
    logger.info("alerts: %d alert emails for %d people with Alerts on (%d Saved Filters)",
                len(emails), len(subscribers), sum(len(p.saved_filters) for p in subscribers))
    for email in emails:
        out.write(f"To: {email.to}\nSubject: {email.subject}\n\n{email.text}\n{'─' * 72}\n")
    return emails
