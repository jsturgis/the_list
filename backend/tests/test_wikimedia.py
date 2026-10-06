"""Tests for finding a Band's photo on Wikimedia Commons through its MusicBrainz Wikidata link."""
from __future__ import annotations

import httpx
import pytest

from app.ingestion.wikimedia import commons_photo

_LINKS = [
    {"type": "free streaming", "url": "https://open.spotify.com/artist/6159IBm5gLPwG4BcJXseXc"},
    {"type": "wikidata", "url": "https://www.wikidata.org/wiki/Q1137217"},
]
_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/Q1137217.json"
_COMMONS = "https://commons.wikimedia.org/w/api.php"


def _entity(*files):
    claims = {"P18": [{"mainsnak": {"datavalue": {"value": f}}} for f in files]} if files else {}
    return {"entities": {"Q1137217": {"claims": claims}}}


def _imageinfo(artist='<a href="//commons.wikimedia.org/wiki/User:S._Bollmann" title="User:S. Bollmann">S. Bollmann</a>',
               license="CC BY-SA 4.0", license_url="https://creativecommons.org/licenses/by-sa/4.0"):
    meta = {"Artist": {"value": artist}, "LicenseShortName": {"value": license}}
    if license_url:
        meta["LicenseUrl"] = {"value": license_url}
    return {"query": {"pages": {"1": {"imageinfo": [{
        "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/44/Soulfly.jpg/960px-Soulfly.jpg"
                    "?utm_source=commons.wikimedia.org&utm_campaign=imageinfo",
        "url": "https://upload.wikimedia.org/wikipedia/commons/4/44/Soulfly.jpg",
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Soulfly_Rockharz_2015_05.jpg",
        "extmetadata": meta,
    }]}}}}


def _client(entity=None, imageinfo=None, *, fail=None):
    """Wikidata answers `entity`, Commons answers `imageinfo`; `fail` makes one of them error out."""
    def handler(request):
        url = str(request.url)
        if url.startswith(_ENTITY):
            if fail == "wikidata":
                raise httpx.ConnectTimeout("slow", request=request)
            return httpx.Response(200, json=entity) if entity is not None else httpx.Response(404)
        if url.startswith(_COMMONS):
            if fail == "commons":
                return httpx.Response(503)
            return httpx.Response(200, json=imageinfo)
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_finds_the_photo_and_its_credit():
    photo = commons_photo(_LINKS, _client(_entity("Soulfly Rockharz 2015 05.jpg"), _imageinfo()))
    assert photo.url == "https://upload.wikimedia.org/wikipedia/commons/thumb/4/44/Soulfly.jpg/960px-Soulfly.jpg"
    assert photo.credit == {
        "source": "Wikimedia Commons",
        "author": "S. Bollmann",  # the HTML link reduced to its text
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "source_url": "https://commons.wikimedia.org/wiki/File:Soulfly_Rockharz_2015_05.jpg",
    }


def test_a_photo_without_a_licence_url_still_has_a_credit():
    photo = commons_photo(_LINKS, _client(_entity("x.jpg"), _imageinfo(artist="Jane Doe", license="Public domain",
                                                                         license_url=None)))
    assert photo.credit["author"] == "Jane Doe"
    assert photo.credit["license_url"] is None


def test_an_author_with_markup_and_whitespace_becomes_plain_text():
    photo = commons_photo(_LINKS, _client(_entity("x.jpg"), _imageinfo(artist="<span>Photo by\n  <b>Ana &amp; Bo</b></span>")))
    assert photo.credit["author"] == "Photo by Ana & Bo"


@pytest.mark.parametrize("links", [
    [],                                                                 # no MusicBrainz links
    [{"type": "free streaming", "url": "https://open.spotify.com/artist/1"}],  # no Wikidata link
    [{"type": "wikidata", "url": "https://www.wikidata.org/wiki/not-an-item"}],
])
def test_no_wikidata_link_means_no_photo(links):
    assert commons_photo(links, _client(_entity("x.jpg"), _imageinfo())) is None


def test_a_wikidata_item_without_an_image_means_no_photo():
    assert commons_photo(_LINKS, _client(_entity(), _imageinfo())) is None


@pytest.mark.parametrize("fail", ["wikidata", "commons"])
def test_errors_and_timeouts_mean_no_photo_never_an_exception(fail):
    assert commons_photo(_LINKS, _client(_entity("x.jpg"), _imageinfo(), fail=fail)) is None


def test_a_missing_wikidata_item_means_no_photo():
    assert commons_photo(_LINKS, _client(entity=None)) is None


def _claim(value=None, rank="normal", snaktype="value"):
    snak = {"snaktype": snaktype}
    if value is not None:
        snak["datavalue"] = {"value": value}
    return {"rank": rank, "mainsnak": snak}


def _entity_claims(*claims):
    return {"entities": {"Q1137217": {"claims": {"P18": list(claims)}}}}


def _requested_file(client_calls):
    return next(c for c in client_calls if "commons.wikimedia.org" in c)


def test_prefers_the_preferred_image_and_skips_deprecated_and_valueless_claims():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if str(request.url).startswith(_ENTITY):
            return httpx.Response(200, json=_entity_claims(
                _claim(snaktype="novalue"), _claim("old.jpg", rank="deprecated"), _claim("normal.jpg"),
                _claim("best.jpg", rank="preferred")))
        return httpx.Response(200, json=_imageinfo())
    assert commons_photo(_LINKS, httpx.Client(transport=httpx.MockTransport(handler))) is not None
    assert "best.jpg" in _requested_file(calls)


def test_a_valueless_first_claim_does_not_hide_a_later_image():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if str(request.url).startswith(_ENTITY):
            return httpx.Response(200, json=_entity_claims(_claim(snaktype="somevalue"), _claim("later.jpg")))
        return httpx.Response(200, json=_imageinfo())
    assert commons_photo(_LINKS, httpx.Client(transport=httpx.MockTransport(handler))) is not None
    assert "later.jpg" in _requested_file(calls)


def test_only_deprecated_images_means_no_photo():
    assert commons_photo(_LINKS, _client(_entity_claims(_claim("old.jpg", rank="deprecated")), _imageinfo())) is None
