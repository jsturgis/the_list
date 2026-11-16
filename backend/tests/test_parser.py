"""Tests for the parser of the List's plain text, on an excerpt of Steve's page (fixtures/the_list.txt) and on
single listings."""
from datetime import date
from pathlib import Path

import pytest

from app.ingestion.parser import ListFormatError, RawShow, edition_date, parse_list

_PAGE = (Path(__file__).parent / "fixtures" / "the_list.txt").read_text()
_HEADER = "funk-punk-thrash-ska      Upcoming shows of Interest      November 13, 2026\n\n"


def _parse(*listings: str) -> list[RawShow]:
    return parse_list(_HEADER + "\n".join(listings) + "\n")


@pytest.fixture(scope="module")
def shows() -> list[RawShow]:
    return parse_list(_PAGE)


def _find(shows: list[RawShow], headliner: str) -> RawShow:
    for s in shows:
        if s.bands and s.bands[0].lower() == headliner.lower():
            return s
    pytest.fail(f"No show found with headliner {headliner!r}")


# ── the page ──────────────────────────────────────────────────────────────────


def test_the_edition_date_is_the_headers():
    assert edition_date(_PAGE) == date(2026, 11, 13)


def test_text_without_the_header_isnt_the_list():
    with pytest.raises(ListFormatError):
        edition_date("<html><body>503 Service Unavailable</body></html>")
    with pytest.raises(ListFormatError):
        parse_list("nov 13 fri Band A at the Chapel, S.F. a/a 8pm\n")


def test_every_listing_with_a_venue_is_a_show(shows):
    # 33 listings: "record store day" isn't a Show, and one listing has no " at " before its Venue.
    assert len(shows) == 31
    assert all(s.date and s.venue_name for s in shows)
    assert not any("record store day" in s.raw_text or "Breezers Hopmonk" in s.raw_text for s in shows)


def test_parsing_stops_at_the_legend(shows):
    """The radio shows ("mon  Losin It ...") and the club directory after the legend aren't Shows."""
    assert "All bands deserve" not in shows[-1].raw_text
    assert shows[-1].bands == ["Kings Of Leon", "Dexter And The Moonrocks"]
    assert not any("Zeitgeist" in s.raw_text for s in shows)


def test_parsing_stops_at_legend_even_if_dates_follow():
    shows = _parse("nov 25 Band A at the Chapel, S.F. a/a 8pm",
                   "\xa0*\xa0 All bands deserve 3 stars a/a all ages",
                   "dec 1 Not A Show at the Footer, Nowhere")
    assert [s.bands for s in shows] == [["Band A"]]


# ── dates ─────────────────────────────────────────────────────────────────────


def test_listings_are_dated_from_the_edition(shows):
    assert _find(shows, "A SKy So Black").date == date(2026, 11, 13)
    assert _find(shows, "Swingin' Utters").date == date(2026, 12, 23)


def test_months_before_the_editions_are_next_year(shows):
    assert _find(shows, "Mike Dillon And Punkadelic").date == date(2027, 1, 1)
    assert _find(shows, "Sampa The Great").date == date(2027, 9, 8)


def test_a_listing_just_before_the_edition_is_this_year():
    [show] = _parse("nov 12 thr Band A at the Chapel, S.F. a/a 8pm")
    assert show.date == date(2026, 11, 12)


def test_an_explicit_year_is_used():
    [show] = _parse("jan 15 2028 fri Band A at the Chapel, S.F. a/a 8pm")
    assert show.date == date(2028, 1, 15)


def test_a_misspelt_or_missing_weekday_isnt_part_of_the_lineup(shows):
    assert _find(shows, "Other Lives").bands == ["Other Lives", "Kelcey Ayer"]         # "nov 13 ri Other Lives"
    assert _find(shows, "Membership Meeting").bands == ["Membership Meeting"]          # "dec  5 dsat"
    assert _find(shows, "Oscar Lindsay").date == date(2027, 3, 26)                     # "mar 26 Oscar Lindsay"
    assert _find(shows, "The Red Clay Strays").bands == ["The Red Clay Strays", "St. Paul And The Broken Bones"]


def test_a_lineup_starting_with_a_lowercase_word_keeps_it():
    [show] = _parse("nov 20 the Hails, Meldrop at the Rickshaw Stop, S.F. a/a")
    assert show.bands == ["the Hails", "Meldrop"]


# ── lineups ───────────────────────────────────────────────────────────────────


def test_a_lineup_over_several_lines(shows):
    s = _find(shows, "Yogetsu & Dambi")   # dj Devendra Banhart, first on the bill, isn't a Band
    assert s.bands == ["Yogetsu & Dambi", "Dennis McNally", "Colleen Morton Busch", "Born I", "Chuck Gould",
                       "Roger Hillyard", "Lonely Parrots", "Ben Gustin", "Marc Lesser"]
    assert s.venue_name == "Great American Music Hall"


def test_djs_are_left_out(shows):
    assert _find(shows, "Jon Spencer").bands == ["Jon Spencer", "Genre Is Death", "Fuckwolf"]
    suzy = next(s for s in shows if "dj Suzy" in s.raw_text)
    assert suzy.bands == [] and suzy.venue_name == "the Rickshaw Stop"


def test_b2b_sets_and_repeated_names_are_left_out():
    [show] = _parse("nov 20 fri Band A, dj X b2b dj Y, Skream b2b Benga, Band A, Band B at the Chapel, S.F. a/a 8pm")
    assert show.bands == ["Band A", "Band B"]


def test_a_parenthetical_after_a_band_is_a_note_on_its_act(shows):
    charger = _find(shows, "Charger")
    assert charger.bands == ["Charger", "Ancient Rage", "Phantasmal Abyss", "Commoner"]
    assert charger.act_notes == ["record release", None, None, None]
    assert _find(shows, "Jo Koy").act_notes == ["comedian"]


def test_commas_inside_parentheses_dont_split_the_lineup():
    [show] = _parse("nov 20 fri Black Flag (Greg Ginn, Max Zanelly), Fifteen (Jeff, John) at the Chapel, S.F. a/a 8pm")
    assert show.bands == ["Black Flag", "Fifteen"]
    assert show.act_notes == ["Greg Ginn, Max Zanelly", "Jeff, John"]


def test_strips_per_band_set_times():
    [show] = _parse("nov 28 sat The Coverups (2:30pm), Whateverglades (1:15pm),",
                    "\xa0\xa0 The Black Excellence Band (noon), Salt + (9:25pm)",
                    "\xa0\xa0 at Lefty Gomez Field, S.F. a/a free noon")
    assert show.bands == ["The Coverups", "Whateverglades", "The Black Excellence Band", "Salt +"]
    assert show.act_notes == [None, None, None, None]
    assert (show.price_raw, show.door_time) == ("free", "12pm")


def test_details_before_at_move_to_the_show():
    [show] = _parse("nov 20 fri Unwoman, Hare And Arrow, Brassica a/a $20 8pm",
                    "\xa0\xa0 at Bay Area Makers Farm, 2700 Barbers Point Rd, Alameda")
    assert show.bands == ["Unwoman", "Hare And Arrow", "Brassica"]
    assert (show.age_restriction, show.price_raw, show.door_time) == ("a/a", "$20", "8pm")
    assert show.city == "Alameda"


def test_venue_details_win_over_details_before_at():
    [show] = _parse("nov 20 fri Band A 8pm at the Chapel, S.F. 21+ $15 9pm")
    assert show.bands == ["Band A"]
    assert (show.age_restriction, show.price_raw, show.door_time) == ("21+", "$15", "9pm")


def test_band_names_ending_in_free_or_symbols_are_kept():
    [show] = _parse("nov 20 fri Set Me Free, TheArti$t at Shoreline Amphitheater, Mountain View a/a $40+ 5pm")
    assert show.bands == ["Set Me Free", "TheArti$t"]


# ── where the Venue starts ────────────────────────────────────────────────────


def test_an_at_inside_a_note_doesnt_start_the_venue(shows):
    tyla = _find(shows, "Tyla")
    assert tyla.bands == ["Tyla", "Jae Stephens"]
    assert tyla.venue_name == "the Fox Theater Oakland"   # no comma: the city is split off in steve_list.py
    assert tyla.notes == "was listed as at the SF Civic Auditorium"
    assert (tyla.door_time, tyla.price_raw, tyla.is_no_reentry) == ("8pm", "$74.65+", True)


def test_an_at_in_the_street_address_doesnt_start_the_venue(shows):
    s = _find(shows, "Ben Goldberg's Brainchild")
    assert s.bands[-1] == "Francis Wong/Chris Trinidad"
    assert (s.venue_name, s.venue_address, s.city) == ("Temescal Arts Center", "511 48th St. at Telegraph", "Oakland")


def test_a_doubled_at_and_a_venue_named_with_one(shows):
    s = _find(shows, "Rosewater")
    assert s.bands == ["Rosewater", "Dave Ellis", "Crispy & Friends", "Cassidy Lyn"]
    assert (s.venue_name, s.city) == ("On Broadway at Mabuhay Gardens", "S.F.")


@pytest.mark.parametrize("line, name, street, city", [
    ("nov 19 thr Band at Felton Music Hall, 6275 Hwy 9, Felton a/a $20 9pm",
     "Felton Music Hall", "6275 Hwy 9", "Felton"),
    ("nov 19 thr Band at Jade Cathey Resturant, 1339 N. 1st St., San Jose a/a $15 7pm",
     "Jade Cathey Resturant", "1339 N. 1st St.", "San Jose"),
    ("nov 19 thr Band at 924 Gilman Street, Berkeley a/a $10 7pm",
     "924 Gilman Street", None, "Berkeley"),
    ("nov 19 thr Band at Folsom Street Fair, 9th Streets Stage, S.F. 18+ 11am",
     "Folsom Street Fair, 9th Streets Stage", None, "S.F."),
])
def test_street_address_is_split_from_venue_name(line, name, street, city):
    [show] = _parse(line)
    assert (show.venue_name, show.venue_address, show.city) == (name, street, city)


# ── details ───────────────────────────────────────────────────────────────────


def test_age_price_and_times(shows):
    s = _find(shows, "A SKy So Black")
    assert (s.venue_name, s.city) == ("924 Gilman Street", "Berkeley")
    assert (s.age_restriction, s.price_raw, s.door_time, s.set_time) == ("a/a", "$18/$20", "6:30pm", "7pm")
    assert _find(shows, "Sampa The Great").price_raw == "$20/$22.50/$25"
    assert _find(shows, "Jim Lauderdale").price_raw == "$53.37-$35.75"


def test_noon_is_a_time(shows):
    s = _find(shows, "Punk Yoga")   # "a/a $5-$10 noon til 1:15pm"
    assert (s.door_time, s.set_time, s.city) == ("12pm", None, "Berkeley")


def test_unknown_details_are_dropped():
    [show] = _parse("nov 20 fri Band A at the Chapel, S.F. a/a ?/?")
    assert (show.city, show.door_time, show.notes) == ("S.F.", None, None)


def test_flags(shows):
    l7 = _find(shows, "L7")                # "# $"
    assert (l7.is_no_reentry, l7.will_sell_out, l7.is_pit) == (True, True, False)
    ceremony = _find(shows, "Ceremony")    # "$37+ 7pm/8pm # @"
    assert (ceremony.is_no_reentry, ceremony.is_pit, ceremony.will_sell_out) == (True, True, False)
    assert ceremony.price_raw == "$37+"
    assert _find(shows, "Oct").is_drink_tickets is True
    [starred] = _parse("nov 20 fri Band A at the Chapel, S.F. a/a 8pm *")
    assert starred.is_recommended is True


def test_notes_in_parentheses(shows):
    assert _find(shows, "Locked Shut").notes == "upstairs"
    assert _find(shows, "Jon Spencer").notes == "sold out"
    assert _find(shows, "Yogetsu & Dambi").notes == "$160 seated"
    assert _find(shows, "Yogetsu & Dambi").price_raw == "$60"


# ── status ────────────────────────────────────────────────────────────────────


def test_upcoming_is_the_default(shows):
    assert _find(shows, "L7").status == "upcoming"


def test_postponed_and_cancelled(shows):
    postponed = _find(shows, "Francisca Valenzuela")
    assert (postponed.status, postponed.venue_name, postponed.city) == ("postponed", "Rickshaw Stop", "S.F.")
    cancelled = _find(shows, "Prayers")
    assert (cancelled.status, cancelled.bands[-1]) == ("cancelled", "Chriz Amaya")


def test_an_incorrect_listing_is_cancelled_with_a_note(shows):
    s = next(s for s in shows if "INCORRECT LISTING" in s.raw_text)
    assert (s.status, s.notes, s.venue_name) == ("cancelled", "incorrect listing", "August Hall")
