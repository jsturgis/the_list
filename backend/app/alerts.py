"""The weekly Alerts: each person's Saved Filters run against the Upcoming Shows, one email per person.

People, their Saved Filters and whether their Alerts are on live in Supabase (ADR 0003); this reads them with
the project's secret key. Each Saved Filter stores the Shows list's URL query string, which becomes the same
filters the GraphQL `shows` query takes, so an Alert lists exactly what the site shows for that filter.

Each email goes out through Resend with an HTML and a plain-text version, and an unsubscribe link (in the
footer and the List-Unsubscribe header) to the site's Unsubscribe page. A dry run prints them instead.
"""
from __future__ import annotations

import html
import logging
import time
from dataclasses import dataclass, field
from typing import TextIO
from urllib.parse import parse_qs

import httpx
from sqlalchemy.orm import Session

from app.clock import local_today
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


class SendError(RuntimeError):
    pass


_RESEND_URL = "https://api.resend.com/emails"
# Resend allows a couple of requests a second; space the sends out under that.
_SEND_INTERVAL = 0.6


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
    date_label: str  # "Sat, Oct 3"
    weekday: str  # "Sat"
    day: str  # "Oct 3"
    headliner: str
    support: list[str]  # up to three supporting Acts
    more_acts: int  # Acts beyond those
    venue: str
    city: str
    doors: str | None  # "8 PM", "7:30 PM"
    price: str | None  # "Free", "$15", "$15–$20"
    age: str | None  # "All Ages", "21+"
    is_pick: bool  # Steve's Pick
    sold_out: bool
    will_sell_out: bool
    url: str


@dataclass
class Section:
    """One Saved Filter's matches in an Alert."""

    name: str
    shows: list[ShowLine]  # the first SHOWS_PER_FILTER matches
    total: int  # every match
    see_all_url: str
    show_ids: frozenset[int] = frozenset()  # every match, for counting Shows across Saved Filters


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


# Every URL param the Shows filter reads (frontend lib/filters FILTER_PARAMS).
_FILTER_PARAMS = ("q", *_LEGACY_SEARCH_PARAMS, "region", "fromDate", "toDate", "priceMax", "free", "age", "genre")


def canonical_query(query: str) -> str:
    """A Saved Filter's query in one form, so two selecting the same Shows compare equal; the twin of frontend
    canonicalQuery: params sorted, old band/venue read as the search, search and genre lower case."""
    params = {k: v[0].strip() for k, v in parse_qs(query).items() if v and v[0].strip()}
    search = (params.get("q") or " ".join(params[k] for k in _LEGACY_SEARCH_PARAMS if k in params)).lower()
    out = {"q": " ".join(search.split())} if search.strip() else {}
    for key in _FILTER_PARAMS:
        if key not in ("q", *_LEGACY_SEARCH_PARAMS) and key in params:
            out[key] = params[key].lower() if key == "genre" else params[key]
    return "&".join(f"{k}={v}" for k, v in sorted(out.items()))


def _matching_shows(db: Session, query: str) -> list[Show]:
    shows = query_shows(db, filters_from_query(query), limit=100_000, offset=0)
    # The site lists a day's Shows by door time (frontend filterShows); unknown door times first.
    return sorted(shows, key=lambda s: (s.date, s.door_time.isoformat() if s.door_time else ""))


def _price(show: Show) -> str | None:
    """As the site shows it (frontend formatPrice): "Free", "$15", "$15–$20"; None when unknown."""
    if show.is_free:
        return "Free"
    if show.price_min is None:
        return None
    lo = f"${show.price_min:,.0f}"
    if show.price_max is None or show.price_max == show.price_min:
        return lo
    return f"{lo}–${show.price_max:,.0f}"


def _doors(show: Show) -> str | None:
    t = show.door_time
    if t is None:
        return None
    hour = t.hour % 12 or 12
    return f"{hour}{f':{t.minute:02d}' if t.minute else ''} {'AM' if t.hour < 12 else 'PM'}"


def _age(show: Show) -> str | None:
    age = show.age_restriction.value if show.age_restriction else None
    return None if age in (None, "unknown") else ("All Ages" if age == "a/a" else age)


def _show_line(show: Show, site: str) -> ShowLine:
    names = [a.band.name for a in sorted(show.acts, key=lambda a: a.position)]
    return ShowLine(
        show_id=show.id,
        date_label=f"{show.date:%a, %b} {show.date.day}",
        weekday=f"{show.date:%a}",
        day=f"{show.date:%b} {show.date.day}",
        headliner=names[0] if names else "Unknown",
        support=names[1:4],
        more_acts=max(0, len(names) - 4),
        venue=show.venue.name,
        city=show.venue.city,
        doors=_doors(show),
        price=_price(show),
        age=_age(show),
        is_pick=bool(show.is_recommended),
        sold_out=bool(show.is_sold_out),
        will_sell_out=bool(show.will_sell_out),
        url=f"{site}/shows/{show.id}/",
    )


# ── emails ────────────────────────────────────────────────────────────────────

def _match_count(sections: list[Section]) -> int:
    """Upcoming Shows matching any of the Saved Filters, each counted once (not only those listed)."""
    return len(frozenset().union(*(s.show_ids for s in sections)))


def _shows(count: int) -> str:
    return f"{count} upcoming {'show' if count == 1 else 'shows'}"


def _subject(sections: list[Section]) -> str:
    return f"{_shows(_match_count(sections))} matched your saved search"


def _intro(sections: list[Section]) -> str:
    """The email's opening line, in the subject's words."""
    return f"{_subject(sections)}."


def _details(line: ShowLine) -> str:
    """ "Doors 8 PM · $15 · 21+" from whatever's known."""
    return " · ".join(x for x in (f"Doors {line.doors}" if line.doors else None, line.price, line.age) if x)


def _marks(line: ShowLine) -> list[str]:
    return [m for m, on in (("Steve's Pick", line.is_pick), ("Sold out", line.sold_out),
                            ("Will sell out", line.will_sell_out)) if on]


def _text(sections: list[Section], site: str, unsubscribe_url: str) -> str:
    """The plain-text version, laid out like the HTML: header, intro, a heading per Saved Filter, footer."""
    lines = ["THE LIST · SF Bay Area Music", "",
             _intro(sections)]
    for s in sections:
        heading = f"{s.name} · {s.total} {'show' if s.total == 1 else 'shows'}"
        lines += ["", heading, "=" * len(heading)]
        for line in s.shows:
            support = ", ".join(line.support) + (f" + {line.more_acts} more" if line.more_acts else "")
            lines += ["", f"{line.date_label} · {line.headliner}",
                      *([f"  with {support}"] if support else []),
                      f"  {line.venue} · {line.city}",
                      *([f"  {_details(line)}"] if _details(line) else []),
                      *([f"  {' · '.join(_marks(line))}"] if _marks(line) else []),
                      f"  {line.url}"]
        if s.total > len(s.shows):
            lines += ["", f"See all {s.total} on The List: {s.see_all_url}"]
    lines += ["", "—", "You set up these alerts on The List.", f"Manage your alerts: {site}/alerts/",
              f"Unsubscribe from these emails: {unsubscribe_url}"]
    return "\n".join(lines) + "\n"


# Email clients ignore stylesheets and many CSS features, so the HTML is tables with inline styles, in the
# site's colours (zinc greys, amber-700 accent).
_INK, _SOFT, _MUTED, _LINE, _ACCENT, _BG = "#18181b", "#52525b", "#71717a", "#e4e4e7", "#b45309", "#f4f4f5"
_HEADER = "#52525b"  # zinc-600: white on it is about 7.7:1
_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
_MARK_STYLES = {
    "Steve's Pick": "background:#fef3c7; color:#92400e",
    "Sold out": "background:#fee2e2; color:#b91c1c",
    "Will sell out": "background:#ffedd5; color:#c2410c",
}


def _html_show(line: ShowLine) -> str:
    e = html.escape
    support = ", ".join(line.support) + (f" + {line.more_acts} more" if line.more_acts else "")
    marks = "".join(f'<span style="display:inline-block; margin:6px 6px 0 0; padding:2px 8px; border-radius:10px; '
                    f'font-size:11px; font-weight:600; {_MARK_STYLES[m]}">{e(m)}</span>' for m in _marks(line))
    details = _details(line)
    return (
        f'<tr><td style="padding:14px 0; border-top:1px solid {_LINE}; vertical-align:top; width:64px">'
        f'<div style="font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:{_ACCENT}">'
        f'{e(line.weekday)}</div><div style="font-size:15px; font-weight:600; color:{_INK}">{e(line.day)}</div></td>'
        f'<td style="padding:14px 0 14px 12px; border-top:1px solid {_LINE}; vertical-align:top">'
        f'<a href="{e(line.url)}" style="font-size:16px; font-weight:700; color:{_INK}; text-decoration:none">'
        f'{e(line.headliner)}</a>'
        + (f'<div style="font-size:13px; color:{_SOFT}; margin-top:2px">with {e(support)}</div>' if support else "")
        + f'<div style="font-size:13px; color:{_SOFT}; margin-top:4px">{e(line.venue)} · {e(line.city)}</div>'
        + (f'<div style="font-size:12px; color:{_MUTED}; margin-top:2px">{e(details)}</div>' if details else "")
        + marks
        + "</td></tr>"
    )


def _html(sections: list[Section], site: str, unsubscribe_url: str) -> str:
    e = html.escape
    preview = ", ".join(dict.fromkeys(line.headliner for s in sections for line in s.shows))[:140]
    body = []
    for s in sections:
        count = f"{s.total} {'show' if s.total == 1 else 'shows'}"
        body.append(
            f'<tr><td style="padding:28px 24px 4px"><table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0"><tr><td style="font-size:18px; font-weight:700; color:{_INK}">{e(s.name)}</td>'
            f'<td style="text-align:right; font-size:13px; color:{_MUTED}; white-space:nowrap">{count}</td></tr>'
            f'</table></td></tr><tr><td style="padding:0 24px"><table role="presentation" width="100%" '
            f'cellpadding="0" cellspacing="0">{"".join(_html_show(line) for line in s.shows)}</table></td></tr>'
        )
        if s.total > len(s.shows):
            body.append(
                f'<tr><td style="padding:12px 24px 0"><a href="{e(s.see_all_url)}" style="display:inline-block; '
                f'padding:9px 16px; border:1px solid {_ACCENT}; border-radius:6px; color:{_ACCENT}; font-size:14px; '
                f'font-weight:600; text-decoration:none">See all {s.total} on The List &rarr;</a></td></tr>'
            )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        # On phones the card fills the screen: no margin around it, no rounded corners.
        '<style>@media (max-width: 620px) { .alert-outer { padding: 0 !important; } '
        '.alert-card { border-radius: 0 !important; } }</style></head>'
        f'<body style="margin:0; padding:0; background:{_BG}">'
        f'<div style="display:none; max-height:0; overflow:hidden">{e(preview)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG}">'
        f'<tr><td class="alert-outer" align="center" style="padding:24px 12px">'
        f'<table class="alert-card" role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px; background:#ffffff; border-radius:12px; overflow:hidden; font-family:{_FONT}">'
        f'<tr><td style="background:{_HEADER}; padding:20px 24px; border-bottom:4px solid #f59e0b">'
        f'<a href="{e(site)}/" style="color:#ffffff; text-decoration:none; font-size:22px; font-weight:800">The List</a>'
        f'<span style="color:#e4e4e7; font-size:14px; margin-left:8px">SF Bay Area Music</span></td></tr>'
        f'<tr><td style="padding:24px 24px 0; font-size:15px; color:{_SOFT}">{e(_intro(sections))}</td></tr>'
        + "".join(body)
        + f'<tr><td style="padding:32px 24px 24px; font-size:12px; color:{_MUTED}; border-top:1px solid {_LINE}">'
        f'You set up these alerts on The List. <a href="{e(site)}/alerts/" style="color:{_MUTED}">Manage your alerts</a>'
        f' · <a href="{e(unsubscribe_url)}" style="color:{_MUTED}">Unsubscribe</a>'
        f'</td></tr></table></td></tr></table></body></html>'
    )


def unsubscribe_url(site: str, token: str) -> str:
    """The site's Unsubscribe page for one person: it turns their Alerts off without signing in."""
    return f"{site}/alerts/unsubscribe/?token={token}"


def build_alerts(db: Session, subscribers: list[Subscriber], site: str) -> list[AlertEmail]:
    """One Alert per person whose Saved Filters match any Upcoming Shows; nothing for the rest."""
    emails = []
    cache: dict[str, list[Show]] = {}  # people often save the same filters
    for person in subscribers:
        sections = []
        seen: set[str] = set()
        for saved in person.saved_filters:
            # Alerts on the same filters (saved before the site stopped duplicates) appear once, under the first.
            same = canonical_query(saved.query)
            if same in seen:
                continue
            seen.add(same)
            if saved.query not in cache:
                cache[saved.query] = _matching_shows(db, saved.query)
            matches = cache[saved.query]
            if matches:
                sections.append(Section(saved.name, [_show_line(s, site) for s in matches[:SHOWS_PER_FILTER]],
                                        len(matches), f"{site}/?{saved.query}", frozenset(s.id for s in matches)))
        if sections:
            unsubscribe = unsubscribe_url(site, person.unsubscribe_token)
            emails.append(AlertEmail(person.email, person.unsubscribe_token, _subject(sections), sections,
                                     _text(sections, site, unsubscribe), _html(sections, site, unsubscribe)))
    return emails


def send_email(email: AlertEmail, site: str) -> None:
    """Send one Alert through Resend, with both versions and a List-Unsubscribe header."""
    response = httpx.post(
        _RESEND_URL,
        json={
            "from": settings.alerts_from,
            "to": [email.to],
            "subject": email.subject,
            "html": email.html,
            "text": email.text,
            "headers": {"List-Unsubscribe": f"<{unsubscribe_url(site, email.unsubscribe_token)}>"},
        },
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            # Resend drops a repeat of the same key, so re-running the job on the same day emails nobody twice.
            "Idempotency-Key": f"alert-{local_today().isoformat()}-{email.unsubscribe_token}",
        },
        timeout=30.0,
    )
    response.raise_for_status()


def run_alerts(db: Session, *, dry_run: bool, out: TextIO, only: str | None = None) -> list[AlertEmail]:
    """Build this week's Alerts and send them; a dry run prints them to `out` instead.

    `only` limits the run to one recipient (by email address), for a test send. A failed send doesn't stop
    the others, but the run raises SendError at the end.
    """
    if not dry_run and not settings.resend_api_key:
        raise SendError("RESEND_API_KEY must be set to send Alerts")
    subscribers = fetch_subscribers()
    if only:
        subscribers = [p for p in subscribers if p.email.lower() == only.strip().lower()]
        logger.info("alerts: limited to one recipient (--only)")
    site = settings.site_url.rstrip("/")
    emails = build_alerts(db, subscribers, site)
    logger.info("alerts: %d alert emails for %d people with Alerts on (%d Saved Filters)",
                len(emails), len(subscribers), sum(len(p.saved_filters) for p in subscribers))
    if dry_run:
        for email in emails:
            out.write(f"To: {email.to}\nSubject: {email.subject}\n\n{email.text}\n{'─' * 72}\n")
        return emails

    failed = 0
    for i, email in enumerate(emails):
        if i:
            time.sleep(_SEND_INTERVAL)
        try:
            send_email(email, site)
        except Exception as exc:
            failed += 1
            # The error comes from Resend's response, not the address; log the kind of failure only.
            logger.error("alerts: a send failed: %s", type(exc).__name__)
    logger.info("alerts: sent %d of %d alert emails", len(emails) - failed, len(emails))
    if failed:
        raise SendError(f"{failed} of {len(emails)} alert emails failed to send")
    return emails
