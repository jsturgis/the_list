"""Tests for page slugs: the names in Band, Venue and Show page URLs."""
from __future__ import annotations

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
