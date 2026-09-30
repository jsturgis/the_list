from __future__ import annotations

"""Parse raw Steve List plain-text email body into RawShow records."""
import re
from dataclasses import dataclass, field
from datetime import date

_NBSP = "\xa0"

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_RE = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"\s+(\d{1,2})(?:\s+(\d{4}))?(?:\s+(mon|tue|wed|thr|fri|sat|sun))?(?=\s|$)",
    re.IGNORECASE,
)

_TIME_RE = re.compile(
    r"(\d{1,2}(?::\d{2})?(?:am|pm))"
    r"(?:[/\\](\d{1,2}(?::\d{2})?(?:am|pm)))?"
    r"(?:\s+til\s+\d{1,2}(?::\d{2})?(?:am|pm))?",
    re.IGNORECASE,
)

_PRICE_RE = re.compile(
    r"(?:free|\$[\d.]+(?:[/\-]\$[\d.]+)*\+?)",
    re.IGNORECASE,
)

_AGE_RE = re.compile(r"\b(a/a|\d{1,2}\+)(?!\w)", re.IGNORECASE)
_STATUS_RE = re.compile(r"^(CANCELLED|POSTPONED)[:\s\xa0]+", re.IGNORECASE)
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


def _extract_year(text: str) -> int:
    m = re.search(r"\b(20\d{2})\b", text[:500])
    return int(m.group(1)) if m else date.today().year


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

    tm = _TIME_RE.search(s)
    if tm:
        result["door_time"] = tm.group(1)
        result["set_time"] = tm.group(2)
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


def _parse_bands_str(s: str) -> tuple[str, list[str]]:
    status = "upcoming"
    sm = _STATUS_RE.match(s)
    if sm:
        status = sm.group(1).lower()
        s = s[sm.end():].strip()
    s = s.replace(_NBSP, " ")
    raw = [_SET_TIME_SUFFIX_RE.sub("", b).strip() for b in s.split(",")]
    bands = [b for b in raw if b and not _DJ_RE.match(b) and not _B2B_RE.search(b)]
    bands = list(dict.fromkeys(bands))
    return status, bands


def parse_email_body(plain_text: str) -> list[RawShow]:
    """Parse decoded email plain text into a list of RawShow records."""
    base_year = _extract_year(plain_text)
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
        if not dm:
            continue

        month = _MONTH_MAP[dm.group(1).lower()]
        day = int(dm.group(2))
        year = int(dm.group(3)) if dm.group(3) else base_year

        try:
            show_date = date(year, month, day)
        except ValueError:
            continue

        parts: list[str] = []
        after_date = first[dm.end():].strip().replace(_NBSP, " ")
        if after_date:
            parts.append(after_date)
        for line in block[1:]:
            cleaned = line.lstrip(_NBSP).strip().replace(_NBSP, " ")
            if cleaned:
                parts.append(cleaned)

        content = " ".join(parts)

        # Split on the last ' at ' to separate band list from venue
        at_idx = content.rfind(" at ")
        if at_idx < 0:
            continue

        bands_str = content[:at_idx].strip()
        venue_str = content[at_idx + 4:].strip()

        # Details occasionally sit before " at " instead of after the venue; move them out of the
        # last band name and use them for any fields the venue part doesn't provide.
        details = ""
        dm_ = _TRAILING_DETAILS_RE.search(bands_str)
        if dm_ and dm_.start() > 0:
            details = dm_.group(0)
            bands_str = bands_str[: dm_.start()]

        status, bands = _parse_bands_str(bands_str)
        venue_data = _parse_venue_part(venue_str)
        if details:
            extra = _parse_venue_part(details)
            for key in ("age_restriction", "price_raw", "door_time", "set_time"):
                if venue_data[key] is None:
                    venue_data[key] = extra[key]

        shows.append(RawShow(
            raw_text=raw_text,
            date=show_date,
            bands=bands,
            status=status,
            **venue_data,
        ))

    return shows
