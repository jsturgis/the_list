"""Tests for finding a Band's photo on its Bandcamp page."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.ingestion.bandcamp import BandcampUnavailable, bandcamp_photo

_PAGE = "https://sunblindhc.bandcamp.com/"
# The parts of a Bandcamp artist page that matter: the band photo in the sidebar, and the header (here a logo).
_HTML = """<html><head><meta property="og:image" content="https://f4.bcbits.com/img/0045628516_23.jpg"></head>
<body><div id="customHeader"><img src="https://f4.bcbits.com/img/0045623952_100.png"></div>
<a class="popupImage" href="https://f4.bcbits.com/img/0045628516_10.jpg">
<img src="https://f4.bcbits.com/img/0045628516_21.jpg" class="band-photo" alt="Sunblind image"></a></body></html>"""


@pytest.fixture(autouse=True)
def no_waiting():
    with patch("app.ingestion.links._sleep"):
        yield


def _client(*responses):
    """Answers each request with the next of `responses` (a status, or HTML for a 200)."""
    answers = iter(responses)

    def handler(request):
        answer = next(answers)
        return httpx.Response(answer) if isinstance(answer, int) else httpx.Response(200, text=answer)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_the_band_photo_at_full_size_credited_to_its_page():
    photo = bandcamp_photo(_PAGE, _client(_HTML))
    assert photo.url == "https://f4.bcbits.com/img/0045628516_10.jpg"
    assert photo.credit == {"source": "Bandcamp", "author": None, "license": None, "license_url": None,
                            "source_url": _PAGE}


def test_a_page_without_a_band_photo_or_one_thats_gone_has_none():
    assert bandcamp_photo(_PAGE, _client("<html><body>no photo</body></html>")) is None
    assert bandcamp_photo(_PAGE, _client(404)) is None


def test_waits_out_a_rate_limit_then_reads_the_page():
    assert bandcamp_photo(_PAGE, _client(429, 429, _HTML)).url == "https://f4.bcbits.com/img/0045628516_10.jpg"


def test_a_page_bandcamp_wont_serve_right_now_is_unavailable_not_photoless():
    with pytest.raises(BandcampUnavailable):
        bandcamp_photo(_PAGE, _client(*[429] * 5))
    with pytest.raises(BandcampUnavailable):
        bandcamp_photo(_PAGE, _client(503))

    def refuse(request):
        raise httpx.ConnectError("no route", request=request)
    with pytest.raises(BandcampUnavailable):
        bandcamp_photo(_PAGE, httpx.Client(transport=httpx.MockTransport(refuse)))
