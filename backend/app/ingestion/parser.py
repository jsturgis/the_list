"""Parse the plain text of Steve's List (https://stevelist.com/list) into RawShow records.

The page is typed by hand: a banner, a header line with the edition date ("Upcoming shows of Interest
November 13, 2026"), then one listing per Show, a legend for the flags, radio shows and a club directory.

    nov 13 fri Charger (record release), Ancient Rage, Phantasmal Abyss, Commoner
           at Gilman Brewing Co., 912 Gilman Street, Berkeley a/a $20/$25 7pm/8pm

Listings have no year (it follows from the edition date, and from the weekday for a date just before it), and
typos: a misspelt or missing weekday, a city run into what follows it. What can't be read as part of a listing
ends up in its notes rather than being lost.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

_NBSP = "\xa0"

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_RE = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?:\s+(\d{4}))?(?=\s|$)",
    re.IGNORECASE,
)
# The weekday after the date, as Steve types it ("thr" is his Thursday), and its number (Monday is 0).
_WEEKDAY_NUMBERS = {"mon": 0, "tue": 1, "wed": 2, "thr": 3, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_WEEKDAYS = tuple(_WEEKDAY_NUMBERS)
_WEEKDAY_TOKEN_RE = re.compile(r"^\s*([a-z]{2,4})\s+")
# Lowercase words a lineup can start with that look a little like a weekday.
_NOT_WEEKDAYS = {"the", "thee", "dj", "an", "a"}
# The header's edition date: "Upcoming shows of Interest      November 13, 2026".
_EDITION_DATE_RE = re.compile(r"\b([A-Z][a-z]+)\s+(\d{1,2}),\s+(20\d{2})\b")
_HEADER_LINES = 20
# A listing dated more than this before the edition is next year's: the List only looks ahead. An edition stays up
# through its week and Steve dates the page the day he updates it, so a listing before the edition is a few days
# old at most; a month leaves room for a late update without taking a listing 11 months out for a past one.
_PAST_LISTING_DAYS = 30

_CLOCK = r"(?:\d{1,2}(?::\d{2})?(?:am|pm)|noon|midnight)"
_TIME_RE = re.compile(
    rf"(?<!\w)({_CLOCK})(?:[/\\]({_CLOCK}))?(?:\s+til\s+{_CLOCK})?(?!\w)",
    re.IGNORECASE,
)
_NAMED_TIMES = {"noon": "12pm", "midnight": "12am"}

_PRICE_RE = re.compile(
    r"(?:free|\$[\d.]+(?:[/\-]\$[\d.]+)*\+?)",
    re.IGNORECASE,
)

_AGE_RE = re.compile(r"\b(a/a|\d{1,2}\+)(?!\w)", re.IGNORECASE)
_STATUS_RE = re.compile(r"^(CANCELLED|CANCELED|POSTPONED|INCORRECT LISTING)[:\s\xa0]+", re.IGNORECASE)
# A listing Steve has marked as wrong isn't happening as listed: it's Cancelled, with a note saying why.
_STATUSES = {"cancelled": "cancelled", "canceled": "cancelled", "postponed": "postponed",
             "incorrect listing": "cancelled"}
_INCORRECT_LISTING_NOTE = "incorrect listing"
# Details Steve doesn't know yet: "a/a ?/?".
_UNKNOWN_RE = re.compile(r"(?<!\S)[?/]+(?!\S)")
# "Charger (record release)": the Band, and a note on its Act. The ")" may be missing.
_PARENTHETICAL_RE = re.compile(r"^(.*?)\s*\((.*?)\)?\s*$", re.DOTALL)
_DJ_RE = re.compile(r"^dj\s+", re.IGNORECASE)
# The flag legend ("* All bands deserve 3 stars ...") follows the last listing; everything after it
# (legend, radio links, EmailOctopus footer) is not show data.
_END_OF_LISTINGS_RE = re.compile(r"^\*\s+All bands deserve", re.IGNORECASE)
_B2B_RE = re.compile(r"\s+b2b\s+", re.IGNORECASE)
# A street address part after the venue name: "6275 Hwy 9", "1339 N. 1st St." (not "9th Street Stage").
_STREET_RE = re.compile(r"^\d+[a-z]?\s+\S", re.IGNORECASE)
# Per-band set time after a name: "The Coverups (2:30pm)", "Black Excellence Band (noon)".
_SET_TIME_SUFFIX_RE = re.compile(
    r"\s*\((?:noon|midnight|\d{1,2}(?::\d{2})?\s*(?:am|pm))\)\s*$", re.IGNORECASE
)
# Age/price/time run at the end of the band list, before " at ": "Brassica a/a $20 8pm".
# "free" is deliberately excluded so names like "Set Me Free" survive.
_TRAILING_DETAILS_RE = re.compile(
    r"(?:\s+(?:a/a|\d{1,2}\+|\$[\d.]+(?:[/\-]\$[\d.]+)*\+?"
    r"|\d{1,2}(?::\d{2})?(?:am|pm)(?:/\d{1,2}(?::\d{2})?(?:am|pm))?))+\s*$",
    re.IGNORECASE,
)


@dataclass
class RawShow:
    raw_text: str
    date: date | None = None
    bands: list[str] = field(default_factory=list)
    venue_name: str | None = None
    city: str | None = None
    age_restriction: str | None = None
    price_raw: str | None = None
    door_time: str | None = None
    set_time: str | None = None
    is_recommended: bool = False    # *
    will_sell_out: bool = False     # $
    is_pit: bool = False            # @
    is_drink_tickets: bool = False  # ^
    is_no_reentry: bool = False     # #
    status: str = "upcoming"        # upcoming | cancelled | postponed
    notes: str | None = None
    venue_address: str | None = None  # street address listed after the venue name, if any
    act_notes: list[str | None] = field(default_factory=list)  # one per band: "(record release)" after its name


class ListFormatError(ValueError):
    """The text isn't the List as we know it (no edition date in its header)."""


def edition_date(text: str) -> date:
    """The date in the List's header: the Friday the edition is for."""
    for line in text.replace("\r", "\n").split("\n")[:_HEADER_LINES]:
        for month, day, year in _EDITION_DATE_RE.findall(line):
            try:
                return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date()
            except ValueError:
                continue
    raise ListFormatError("no edition date in the List's header")


def _listing_date(month: int, day: int, year: int | None, weekday: int | None, edition: date) -> date | None:
    """A listing's date. A year Steve typed is used as it is. Otherwise it's the edition's year when that puts it on
    or after the edition, and the next when that would be more than `_PAST_LISTING_DAYS` before it ("jan 15" in a
    November edition). Between the two, the listing's weekday says which: "oct 30 sat" in a November 2026 edition
    is 2027's (Oct 30, 2026 was a Friday). A date falls on different weekdays in consecutive years, so the weekday
    never fits both; when it fits neither (a typo) or there is none, a listing a few days old stays this year's."""
    if year:
        try:
            return date(year, month, day)
        except ValueError:
            return None
    try:
        this_year = date(edition.year, month, day)
    except ValueError:  # feb 29
        this_year = None
    try:
        next_year = date(edition.year + 1, month, day)
    except ValueError:
        next_year = None
    if this_year is None or this_year < edition - timedelta(days=_PAST_LISTING_DAYS):
        return next_year
    if this_year < edition and next_year and next_year.weekday() == weekday != this_year.weekday():
        return next_year
    return this_year


def _weekday(text: str) -> tuple[int | None, str]:
    """The weekday at the start of `text`, however it's spelled ("fri", "ri", "dsat"), and the text after it; None
    and `text` when it doesn't start with one."""
    m = _WEEKDAY_TOKEN_RE.match(text)
    if m and m.group(1) not in _NOT_WEEKDAYS:
        match = difflib.get_close_matches(m.group(1), _WEEKDAYS, n=1, cutoff=0.6)
        if match:
            return _WEEKDAY_NUMBERS[match[0]], text[m.end():]
    return None, text


def _clock(text: str | None) -> str | None:
    return _NAMED_TIMES.get(text.lower(), text) if text else None


def _parse_venue_part(s: str) -> dict:
    result: dict = {
        "venue_name": None, "city": None, "age_restriction": None,
        "price_raw": None, "door_time": None, "set_time": None,
        "is_recommended": False, "will_sell_out": False, "is_pit": False,
        "is_drink_tickets": False, "is_no_reentry": False, "notes": None, "venue_address": None,
    }

    note_parts: list[str] = []

    def _grab(m: re.Match) -> str:
        content = m.group(1).strip()
        if content:
            note_parts.append(content)
        return " "

    s = re.sub(r"\(([^)]*)\)", _grab, s)
    if note_parts:
        result["notes"] = "; ".join(note_parts)

    kept: list[str] = []
    for tok in s.split():
        if tok == "*":
            result["is_recommended"] = True
        elif tok == "$":
            result["will_sell_out"] = True
        elif tok == "@":
            result["is_pit"] = True
        elif tok == "^":
            result["is_drink_tickets"] = True
        elif tok == "#":
            result["is_no_reentry"] = True
        else:
            kept.append(tok)
    s = " ".join(kept)

    s = _UNKNOWN_RE.sub(" ", s)

    tm = _TIME_RE.search(s)
    if tm:
        result["door_time"] = _clock(tm.group(1))
        result["set_time"] = _clock(tm.group(2))
        s = s[: tm.start()] + s[tm.end():]

    pm = _PRICE_RE.search(s)
    if pm:
        p = pm.group(0)
        result["price_raw"] = "free" if p.lower() == "free" else p
        s = s[: pm.start()] + s[pm.end():]

    am = _AGE_RE.search(s)
    if am:
        result["age_restriction"] = am.group(1)
        s = s[: am.start()] + s[am.end():]

    venue_city = re.sub(r"\s+", " ", s).strip().strip(",")
    parts = [p.strip() for p in venue_city.split(",") if p.strip()]
    if len(parts) >= 2:
        result["city"] = parts[-1]
        # "Felton Music Hall, 6275 Hwy 9, Felton": keep the street out of the name. The first part is
        # always the name, since some venues are named by address ("924 Gilman Street").
        name_parts, street_parts = parts[:1], []
        for part in parts[1:-1]:
            (street_parts if _STREET_RE.match(part) else name_parts).append(part)
        result["venue_name"] = ", ".join(name_parts)
        result["venue_address"] = ", ".join(street_parts) or None
    elif parts:
        result["venue_name"] = parts[0]

    return result


def split_venue_street(name: str) -> tuple[str, str | None]:
    """Split "Felton Music Hall, 6275 Hwy 9" into ("Felton Music Hall", "6275 Hwy 9")."""
    parts = [p.strip() for p in name.split(",") if p.strip()]
    if not parts:
        return name, None
    name_parts, street_parts = parts[:1], []
    for part in parts[1:]:
        (street_parts if _STREET_RE.match(part) else name_parts).append(part)
    return ", ".join(name_parts), ", ".join(street_parts) or None


def clean_band_name(name: str) -> str:
    """Strip a trailing "(set time)" and trailing age/price/time from a band name."""
    name = _SET_TIME_SUFFIX_RE.sub("", name).strip()
    m = _TRAILING_DETAILS_RE.search(name)
    if m and m.start() > 0:
        name = name[: m.start()].strip()
    return name


def _split_outside_parentheses(text: str, separator: str) -> list[str]:
    """Split at each `separator` that isn't inside parentheses: "Black Flag (Greg Ginn, Max Zanelly), Fifteen"."""
    parts, depth, current = [], 0, []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        if char == separator and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _find_outside_parentheses(text: str, needle: str) -> int:
    """Index of the first `needle` that isn't inside parentheses, or -1."""
    depth = 0
    for i, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        elif depth == 0 and text.startswith(needle, i):
            return i
    return -1


def _parse_bands_str(s: str) -> tuple[str, list[str], list[str | None], str | None]:
    """(status, bands, a note per band, a note for the Show) from the lineup before " at "."""
    status, show_note = "upcoming", None
    sm = _STATUS_RE.match(s)
    if sm:
        prefix = " ".join(sm.group(1).lower().split())
        status = _STATUSES[prefix]
        show_note = _INCORRECT_LISTING_NOTE if prefix == "incorrect listing" else None
        s = s[sm.end():].strip()
    s = s.replace(_NBSP, " ")
    acts: dict[str, str | None] = {}
    for raw in _split_outside_parentheses(s, ","):
        name, note = _SET_TIME_SUFFIX_RE.sub("", raw).strip(), None
        if "(" in name:
            band, note = _PARENTHETICAL_RE.match(name).groups()
            name, note = (band.strip(), note.strip() or None) if band.strip() else (name, None)
        if name and not _DJ_RE.match(name) and not _B2B_RE.search(name):
            acts.setdefault(name, note)
    return status, list(acts), list(acts.values()), show_note


def _split_listing(lines: list[str]) -> tuple[str, str] | None:
    """(lineup, venue and details) of a listing's lines, the date already off the first; None when it names no Venue.

    The Venue starts at the last line that opens with "at ", else at the first " at " ("Tyla at the Fox Theater
    Oakland a/a 8pm (was listed as at the SF Civic Auditorium)"; "... at Temescal Arts Center, 511 48th St. at
    Telegraph, Oakland").
    """
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].lower().startswith("at "):
            return " ".join(lines[:i]), " ".join(lines[i:])[3:]
    content = " ".join(lines)
    at = _find_outside_parentheses(content, " at ")
    if at < 0:
        return None
    return content[:at], content[at + 4:]


def parse_list(plain_text: str) -> list[RawShow]:
    """Every listing in the List's text, in order. Lines that aren't a Show ("nov 27 fri record store day") and
    listings that name no Venue are left out."""
    edition = edition_date(plain_text)
    text = plain_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _END_OF_LISTINGS_RE.match(line.replace(_NBSP, " ").strip()):
            break
        if _DATE_RE.match(line.lstrip(_NBSP)):
            if current:
                blocks.append(current)
            current = [line]
        elif current and line.strip():
            current.append(line)
    if current:
        blocks.append(current)

    shows: list[RawShow] = []
    for block in blocks:
        raw_text = "\n".join(block)
        first = block[0].lstrip(_NBSP)
        dm = _DATE_RE.match(first)
        weekday, rest = _weekday(first[dm.end():].replace(_NBSP, " "))
        show_date = _listing_date(_MONTH_MAP[dm.group(1).lower()], int(dm.group(2)),
                                  int(dm.group(3)) if dm.group(3) else None, weekday, edition)
        if not show_date:
            continue

        parts = [rest.strip()]
        parts += [line.replace(_NBSP, " ").strip() for line in block[1:]]
        split = _split_listing([p for p in parts if p] or [""])
        if not split:
            continue
        bands_str, venue_str = (part.strip() for part in split)
        # "at at On Broadway", "at the Fillmore": the venue's name starts after them.
        venue_str = re.sub(r"^(?:at\s+)+", "", venue_str)

        # Details occasionally sit before " at " instead of after the venue; move them out of the
        # last band name and use them for any fields the venue part doesn't provide.
        details = ""
        dm_ = _TRAILING_DETAILS_RE.search(bands_str)
        if dm_ and dm_.start() > 0:
            details = dm_.group(0)
            bands_str = bands_str[: dm_.start()]

        status, bands, act_notes, show_note = _parse_bands_str(bands_str)
        venue_data = _parse_venue_part(venue_str)
        if details:
            extra = _parse_venue_part(details)
            for key in ("age_restriction", "price_raw", "door_time", "set_time"):
                if venue_data[key] is None:
                    venue_data[key] = extra[key]
        if show_note:
            venue_data["notes"] = "; ".join(n for n in (show_note, venue_data["notes"]) if n)

        shows.append(RawShow(
            raw_text=raw_text,
            date=show_date,
            bands=bands,
            act_notes=act_notes,
            status=status,
            **venue_data,
        ))

    return shows
