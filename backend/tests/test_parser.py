"""Tests for parse_email_body using the real sample email fixture."""
import email as _email
from pathlib import Path

import pytest

from app.ingestion.parser import RawShow, parse_email_body

_SAMPLE_EML = Path(__file__).parent.parent.parent / "samples" / (
    "San Francisco Area Music List for Friday, September 25th, 2026.eml"
)


@pytest.fixture(scope="module")
def shows() -> list[RawShow]:
    msg = _email.message_from_bytes(_SAMPLE_EML.read_bytes())
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            plain = part.get_payload(decode=True).decode("utf-8")
            return parse_email_body(plain)
    pytest.fail("No text/plain part found in sample email")


def _find(shows: list[RawShow], headliner: str) -> RawShow:
    for s in shows:
        if s.bands and s.bands[0].lower() == headliner.lower():
            return s
    pytest.fail(f"No show found with headliner {headliner!r}")


def _find_venue(shows: list[RawShow], venue: str) -> list[RawShow]:
    return [s for s in shows if s.venue_name and venue.lower() in s.venue_name.lower()]


# ── basic sanity ──────────────────────────────────────────────────────────────


def test_returns_nonempty_list(shows):
    assert len(shows) > 50


def test_all_have_dates(shows):
    assert all(s.date is not None for s in shows)


def test_all_have_venue(shows):
    assert all(s.venue_name is not None for s in shows)


# ── multi-band show ────────────────────────────────────────────────────────────


def test_gilman_multiband(shows):
    """924 Gilman show has 6 bands in order, headliner first."""
    gilman = [s for s in shows if s.venue_name == "924 Gilman Street" and "One Last Prayer" in (s.bands or [])]
    assert gilman, "Gilman show not found"
    s = gilman[0]
    assert s.bands[0] == "One Last Prayer"
    assert "Opposing Force" in s.bands
    assert "Cross Checked" in s.bands
    assert "Neighborhood Threat" in s.bands
    assert "Brute Pressure" in s.bands
    assert "Look Away" in s.bands
    assert len(s.bands) == 6


# ── flags ─────────────────────────────────────────────────────────────────────


def test_flag_no_reentry(shows):
    s = _find(shows, "Beck")
    assert s.is_no_reentry is True


def test_flag_pit_and_no_reentry(shows):
    """Sleep at Fillmore has both # and @."""
    sleep = [s for s in shows if s.bands and s.bands[0] == "Sleep" and "Fillmore" in (s.venue_name or "")]
    assert sleep, "Sleep at Fillmore not found"
    s = sleep[0]
    assert s.is_pit is True
    assert s.is_no_reentry is True


def test_flag_drink_tickets(shows):
    s = _find(shows, "Cheo")
    assert s.is_drink_tickets is True


def test_flag_will_sell_out(shows):
    """Mrs Robinson show ends with $ flag."""
    mrs = [s for s in shows if s.bands and "Mrs Robinson And The Dadbeats" in s.bands]
    assert mrs, "Mrs Robinson show not found"
    assert mrs[0].will_sell_out is True


# ── price parsing ─────────────────────────────────────────────────────────────


def test_price_slash(shows):
    """Rose City Band at the Chapel: $25/$28."""
    chapel = [
        s for s in shows
        if "Chapel" in (s.venue_name or "") and s.bands and s.bands[0] == "Rose City Band"
        and s.date.month == 9 and s.date.day == 25
    ]
    assert chapel, "Rose City Band / Chapel show not found"
    assert chapel[0].price_raw == "$25/$28"


def test_price_free(shows):
    """Kilowatt free show."""
    free_shows = [s for s in shows if s.price_raw == "free"]
    assert free_shows, "No free shows found"


def test_price_raw_preserved(shows):
    """Multi-tier prices stored verbatim."""
    multi = [s for s in shows if s.price_raw and s.price_raw.count("/") >= 3]
    assert multi, "No multi-tier price show found"
    # e.g. $25/$27/$30/$35/$40
    assert any("$25/$27" in s.price_raw for s in multi)


# ── status ────────────────────────────────────────────────────────────────────


def test_cancelled_show(shows):
    cancelled = [s for s in shows if s.status == "cancelled"]
    assert cancelled
    # Badbadnotgood show is cancelled
    assert any("Badbadnotgood" in s.bands for s in cancelled)


def test_postponed_show(shows):
    postponed = [s for s in shows if s.status == "postponed"]
    assert postponed
    assert any("Lionel Richie" in s.bands for s in postponed)


def test_upcoming_is_default(shows):
    assert sum(1 for s in shows if s.status == "upcoming") > 50


# ── DJ / b2b filtering ────────────────────────────────────────────────────────


def test_dj_filtered(shows):
    """No band name starts with 'dj '."""
    all_bands = [b for s in shows for b in s.bands]
    dj_names = [b for b in all_bands if b.lower().startswith("dj ")]
    assert dj_names == [], f"DJ acts not filtered: {dj_names[:5]}"


def test_b2b_filtered(shows):
    """No band name contains ' b2b '."""
    all_bands = [b for s in shows for b in s.bands]
    b2b_names = [b for b in all_bands if " b2b " in b.lower()]
    assert b2b_names == [], f"b2b acts not filtered: {b2b_names[:5]}"


def test_repeated_headliner_deduped(shows):
    """Grant-Lee Phillips is listed twice in the source; keep one Act per Band."""
    hopmonk = [
        s for s in shows
        if s.bands and s.bands[0] == "Grant-Lee Phillips" and "Hopmonk" in (s.venue_name or "")
    ]
    assert hopmonk, "Grant-Lee Phillips / Hopmonk show not found"
    s = hopmonk[0]
    assert s.bands.count("Grant-Lee Phillips") == 1


def test_rickshaw_dj_filtered(shows):
    """Cain Culto show at Rickshaw Stop: dj Aaron Axelsen absent, others present."""
    rickshaw = [
        s for s in shows
        if s.bands and s.bands[0] == "Cain Culto" and "Rickshaw" in (s.venue_name or "")
    ]
    assert rickshaw, "Cain Culto / Rickshaw show not found"
    s = rickshaw[0]
    assert "Cain Culto" in s.bands
    assert "TwoLips" in s.bands
    assert not any("Aaron Axelsen" in b for b in s.bands)


# ── Portola (20+ acts, multi-line) ───────────────────────────────────────────


def test_portola_single_rawshow(shows):
    """Portola (Pier 80) is a single RawShow with 20+ non-DJ/b2b acts."""
    portola = [
        s for s in shows
        if "Pier 80" in (s.venue_name or "") and s.bands and s.bands[0] == "Robyn"
    ]
    assert portola, "Portola (Robyn headliner) show not found"
    assert len(portola) == 1, "Portola should be one show, not split"
    s = portola[0]
    assert len(s.bands) > 20
    assert "Robyn" in s.bands
    assert "Fatboy Slim" in s.bands
    assert "Tricky" in s.bands
    # b2b and DJ acts must be absent
    assert not any("b2b" in b.lower() for b in s.bands)
    assert not any(b.lower().startswith("dj ") for b in s.bands)


# ── venue / city ──────────────────────────────────────────────────────────────


def test_venue_and_city_extracted(shows):
    beck = _find(shows, "Beck")
    assert beck.venue_name is not None
    assert "Masonic" in beck.venue_name
    assert beck.city in ("S.F.", "San Francisco")


def test_venue_with_street_address(shows):
    """Gilman Street address preserved in venue_name; city = Berkeley."""
    gilman = _find_venue(shows, "924 Gilman")
    assert gilman
    assert gilman[0].city == "Berkeley"


# ── dates ─────────────────────────────────────────────────────────────────────


def test_date_sep_25(shows):
    sep25 = [s for s in shows if s.date and s.date.month == 9 and s.date.day == 25]
    assert len(sep25) > 10


def test_future_date_with_explicit_year(shows):
    """Dates like 'may  9 2027' have the correct year."""
    future = [s for s in shows if s.date and s.date.year == 2027]
    assert future, "No 2027 shows found"


# ── end of listings ───────────────────────────────────────────────────────────


def test_last_listing_stops_at_flag_legend(shows):
    """The final listing must not swallow the legend, radio links or EmailOctopus footer."""
    last = max((s for s in shows if s.date), key=lambda s: s.date)
    assert last.bands == ["The Airborne Toxic Event"]
    assert "Guild Theater" in (last.venue_name or "")
    assert "All bands deserve" not in last.raw_text
    assert not any("EmailOctopus" in (s.city or "") or "EmailOctopus" in s.raw_text for s in shows)


def test_parsing_stops_at_legend_even_if_dates_follow():
    text = (
        "sep 25 Band A at the Chapel, S.F. a/a 8pm\n"
        "\xa0*\xa0 All bands deserve 3 stars a/a all ages\n"
        "oct 1 Not A Show at the Footer, Nowhere\n"
    )
    shows = parse_email_body(text)
    assert [s.bands for s in shows] == [["Band A"]]
