"""Tests for splitting joint billings ("Dying Fetus And Sanguisugabogg") into separate Bands."""
from __future__ import annotations

from datetime import date

import pytest

from app.ingestion.joint_bands import fix_joint_band_names, joint_parts, split_joint_acts, split_joint_name
from app.models.act import Act
from app.models.band import Band
from app.models.show import Show
from app.models.venue import Region, Venue

# MusicBrainz as it answered for these names (tag-list: whether the artist has tags/genres).
_MUSICBRAINZ = {
    "Belle and Sebastian": [{"name": "indie pop"}],
    "Tank And The Bangas": [{"name": "soul"}],
    "Dying Fetus": [{"name": "death metal"}],
    "Sanguisugabogg": [{"name": "death metal"}],
    "Gillian Welch": [{"name": "folk"}],
    "David Rawlings": [],
    "Hare": [],             # an untagged Swiss metal band, not this Hare And Arrow
    "Arrow": [],            # an untagged calypso singer
    "Friends": [{"name": "pop"}],
    "Hugel": [{"name": "house"}],
}


def _search(name):
    tags = _MUSICBRAINZ.get(name)
    return None if tags is None else {"id": name, "name": name, "tag-list": tags}


def _tagged(artist):
    return bool(artist.get("tag-list"))


def _split(name):
    return split_joint_name(name, search=_search, tagged=_tagged)


@pytest.mark.parametrize("name, parts", [
    ("Dying Fetus And Sanguisugabogg", ["Dying Fetus", "Sanguisugabogg"]),
    ("Gillian Welch & David Rawlings", ["Gillian Welch", "David Rawlings"]),
    ("Trianna Feruza & The Heavy Hitters", None),   # a backing band
    ("Hugel & Friends", None),
    ("Marty Stuart and His Fabulous Superlatives", None),
    ("Earth Wind And Fire And Water", None),         # more than two parts: left alone
    ("Mdou Moctar", None),
    ("Grandmaster Flash", None),                      # "and" inside a word
])
def test_joint_parts(name, parts):
    assert joint_parts(name) == parts


@pytest.mark.parametrize("name, result", [
    ("Dying Fetus And Sanguisugabogg", ["Dying Fetus", "Sanguisugabogg"]),  # both halves known, the whole isn't
    ("Gillian Welch & David Rawlings", ["Gillian Welch", "David Rawlings"]),  # untagged, but two words
    ("Belle and Sebastian", ["Belle and Sebastian"]),                     # MusicBrainz knows the whole name
    ("Tank And The Bangas", ["Tank And The Bangas"]),
    ("Hare And Arrow", ["Hare And Arrow"]),                               # one-word, untagged namesakes
    ("Hugel & Friends", ["Hugel & Friends"]),                             # never split, though both are known
    ("Brian Mello And The Afterglow", ["Brian Mello And The Afterglow"]),
    ("Kim And Kanye", ["Kim And Kanye"]),                                  # neither half known
])
def test_split_joint_name(name, result):
    assert _split(name) == result


def test_split_joint_acts_rewrites_the_lineup_in_place():
    data = {
        "bands": ["Dying Fetus And Sanguisugabogg", "Belle and Sebastian"],
        "act_notes": ["co-headline", None],
        "band_enrichment": [
            ("Dying Fetus And Sanguisugabogg", {"genres": ["death metal"], "bandcamp_url": "https://x.bandcamp.com/",
                                                "image_url": "https://img/x.jpg", "is_local": False}),
            ("Belle and Sebastian", {"genres": ["indie pop"], "spotify_url": "https://open.spotify.com/artist/1"}),
        ],
    }
    done = split_joint_acts(data, _split)

    assert done == [("Dying Fetus And Sanguisugabogg", ["Dying Fetus", "Sanguisugabogg"])]
    assert data["bands"] == ["Dying Fetus", "Sanguisugabogg", "Belle and Sebastian"]
    assert data["act_notes"] == ["co-headline", None, None]
    # Each half keeps the genres and locality; the billing's own link and image are dropped.
    assert data["band_enrichment"][0] == ("Dying Fetus", {"genres": ["death metal"], "is_local": False})
    assert data["band_enrichment"][1] == ("Sanguisugabogg", {"genres": ["death metal"], "is_local": False})
    assert data["band_enrichment"][2][1]["spotify_url"] == "https://open.spotify.com/artist/1"


def test_split_joint_acts_leaves_a_show_without_joint_billings_alone():
    data = {"bands": ["Belle and Sebastian"], "act_notes": [None], "band_enrichment": [("Belle and Sebastian", {})]}
    before = {k: list(v) for k, v in data.items()}
    assert split_joint_acts(data, _split) == []
    assert data == before


# ── one-off fix ───────────────────────────────────────────────────────────────

def _show(db, day):
    v = db.query(Venue).first() or Venue(name="The Ritz", city="San Jose", region=Region.south_bay)
    s = Show(date=date(2026, 10, day), venue=v)
    db.add(s)
    db.flush()
    return s


def _lineup(show):
    return [(a.position, a.band.name) for a in sorted(show.acts, key=lambda a: a.position)]


def test_fix_splits_existing_joint_bands_on_every_show(db):
    show = _show(db, 5)
    joint = Band(name="Dying Fetus And Sanguisugabogg", genres=["death metal"], is_local=False)
    opener, belle = Band(name="Incite"), Band(name="Belle and Sebastian")
    existing_half = Band(name="Dying Fetus", genres=["brutal death metal"])
    db.add_all([joint, opener, belle, existing_half])
    db.flush()
    db.add_all([Act(show_id=show.id, band_id=joint.id, position=0), Act(show_id=show.id, band_id=opener.id, position=1)])
    other = _show(db, 9)
    db.add(Act(show_id=other.id, band_id=belle.id, position=0))
    db.flush()

    fixes = fix_joint_band_names(db, split=_split, apply=True)

    assert fixes == [("Dying Fetus And Sanguisugabogg", ["Dying Fetus", "Sanguisugabogg"], 1)]
    db.expire_all()
    assert _lineup(show) == [(0, "Dying Fetus"), (1, "Sanguisugabogg"), (2, "Incite")]
    assert db.query(Band).filter(Band.name == "Dying Fetus And Sanguisugabogg").first() is None
    assert db.query(Band).filter(Band.name == "Dying Fetus").one().id == existing_half.id   # reused
    assert db.query(Band).filter(Band.name == "Sanguisugabogg").one().is_local is False      # created
    assert _lineup(other) == [(0, "Belle and Sebastian")]                                     # untouched


def test_fix_is_a_dry_run_by_default(db):
    show = _show(db, 5)
    joint = Band(name="Dying Fetus And Sanguisugabogg")
    db.add(joint)
    db.flush()
    db.add(Act(show_id=show.id, band_id=joint.id, position=0))
    db.commit()

    assert len(fix_joint_band_names(db, split=_split)) == 1
    db.expire_all()
    assert _lineup(show) == [(0, "Dying Fetus And Sanguisugabogg")]
