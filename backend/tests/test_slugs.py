"""Tests for page slugs: the names in Band, Venue and Show page URLs."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.slugs import assign


def band(id, name):
    return SimpleNamespace(id=id, name=name)


def test_a_band_slug_is_its_name_lowercased_and_hyphenated():
    assert assign(bands=[band(1, "The Jon Spencer Blues Explosion")]).bands == {1: "the-jon-spencer-blues-explosion"}


def test_accents_are_dropped():
    assert assign(bands=[band(1, "Sigur Rós"), band(2, "Mötley Crüe")]).bands == {1: "sigur-ros", 2: "motley-crue"}


def test_ampersand_reads_as_and_and_apostrophes_are_dropped():
    assert assign(bands=[band(1, "Simon & Garfunkel"), band(2, "Guns N' Roses"), band(3, "Hell’s Kitchen")]).bands == {
        1: "simon-and-garfunkel", 2: "guns-n-roses", 3: "hells-kitchen"}


def test_a_name_with_nothing_left_is_the_kind_and_id():
    assert assign(bands=[band(7, "!!!"), band(8, "坂本龍一")]).bands == {7: "band-7", 8: "band-8"}


def test_bands_with_one_name_get_their_ids_after_the_first():
    expected = {4: "the-ocean", 9: "the-ocean-9", 12: "the-ocean-12"}
    assert assign(bands=[band(9, "The Ocean"), band(4, "the ocean"), band(12, "The Ocean")]).bands == expected
    assert assign(bands=[band(12, "The Ocean"), band(4, "the ocean"), band(9, "The Ocean")]).bands == expected


def test_a_suffixed_slug_never_takes_another_bands_slug():
    # "Foo 9" is foo-9, so the second Foo can't be foo-9 too.
    slugs = assign(bands=[band(5, "Foo"), band(9, "Foo"), band(3, "Foo 9")]).bands
    assert slugs[5] == "foo" and slugs[3] == "foo-9"
    assert slugs[9] not in {"foo", "foo-9"} and slugs[9].startswith("foo-9")


def test_an_all_digit_slug_gets_the_kind_before_it_so_it_isnt_taken_for_an_id():
    # /bands/311/ is Band 311's numeric URL, redirecting to its slug.
    assert assign(bands=[band(1, "311"), band(2, "The 1975")]).bands == {1: "band-311", 2: "the-1975"}


venue = band  # a Venue needs only an id and a name too


def test_venue_slugs_follow_the_same_rules_with_their_own_kind():
    slugs = assign(venues=[venue(2, "924 Gilman Street"), venue(5, "Bottom of the Hill"), venue(9, "Bottom of the Hill"),
                           venue(11, "???"), venue(12, "1015")]).venues
    assert slugs == {2: "924-gilman-street", 5: "bottom-of-the-hill", 9: "bottom-of-the-hill-9", 11: "venue-11", 12: "venue-1015"}


def test_a_band_and_a_venue_can_share_a_slug():
    slugs = assign(bands=[band(1, "The Chapel")], venues=[venue(1, "The Chapel")])
    assert (slugs.bands, slugs.venues) == ({1: "the-chapel"}, {1: "the-chapel"})


def show(id, date, venue_id, *band_ids):
    return SimpleNamespace(id=id, date=date, venue_id=venue_id,
                           acts=[SimpleNamespace(band_id=b, position=p) for p, b in enumerate(band_ids)])


BANDS = [band(1, "Deafheaven"), band(2, "Uniform"), band(3, "DEAFHEAVEN!")]
VENUES = [venue(1, "Bottom of the Hill"), venue(2, "The Chapel")]


def test_a_show_slug_is_its_headliners_slug_and_date():
    slugs = assign(bands=BANDS, venues=VENUES, shows=[show(10, date(2026, 10, 1), 1, 1, 2), show(11, date(2026, 10, 2), 1, 3)])
    # The headliner's own slug, so two Bands that share a name stay apart.
    assert slugs.shows == {10: "deafheaven-2026-10-01", 11: "deafheaven-3-2026-10-02"}


def test_a_show_without_acts_is_show_and_its_date():
    assert assign(venues=VENUES, shows=[show(10, date(2026, 10, 1), 1)]).shows == {10: "show-2026-10-01"}


def test_shows_with_one_headliner_on_one_date_get_their_venues():
    slugs = assign(bands=BANDS, venues=VENUES, shows=[show(10, date(2026, 10, 1), 2, 1), show(11, date(2026, 10, 1), 1, 1)])
    assert slugs.shows == {10: "deafheaven-the-chapel-2026-10-01", 11: "deafheaven-bottom-of-the-hill-2026-10-01"}


def test_shows_with_one_headliner_at_one_venue_on_one_date_get_their_ids_after_the_first():
    # An early and a late show.
    slugs = assign(bands=BANDS, venues=VENUES, shows=[show(12, date(2026, 10, 1), 1, 1), show(10, date(2026, 10, 1), 1, 1)])
    assert slugs.shows == {10: "deafheaven-bottom-of-the-hill-2026-10-01", 12: "deafheaven-bottom-of-the-hill-2026-10-01-12"}
