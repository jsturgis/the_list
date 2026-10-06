"""Tests for saving Band photos with the data: downloaded, resized to WebP, and stored in the images folder."""
from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image

from app.ingestion.band_photos import MAX_WIDTH, is_stored, save_band_photo, site_path
from app.models.band import Band


def _jpeg(width=1600, height=900, color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "JPEG")
    return buf.getvalue()


_RealClient = httpx.Client  # tests that replace httpx.Client still build clients with this


def _client(routes: dict[str, httpx.Response]) -> httpx.Client:
    """An httpx client that answers from `routes` (URL -> response), 404 for anything else."""
    def handler(request):
        return routes.get(str(request.url), httpx.Response(404))
    return _RealClient(transport=httpx.MockTransport(handler))


def _band(band_id=7, image_url=None):
    return Band(id=band_id, name="Redwood Sirens", image_url=image_url)


def test_downloads_resizes_and_stores_a_photo_as_webp(tmp_path):
    url = "https://img.example/sirens.jpg"
    band = _band(image_url=url)

    assert save_band_photo(band, url, tmp_path, _client({url: httpx.Response(200, content=_jpeg())})) is True

    assert band.image_url.startswith("bands/7-") and band.image_url.endswith(".webp")
    with Image.open(tmp_path / band.image_url) as saved:
        assert saved.format == "WEBP"
        assert saved.size == (MAX_WIDTH, 450)  # aspect ratio kept


def test_a_small_photo_is_not_enlarged(tmp_path):
    url = "https://img.example/small.png"
    band = _band()
    buf = io.BytesIO()
    Image.new("RGBA", (300, 200), (0, 0, 255, 128)).save(buf, "PNG")
    save_band_photo(band, url, tmp_path, _client({url: httpx.Response(200, content=buf.getvalue())}))
    with Image.open(tmp_path / band.image_url) as saved:
        assert saved.size == (300, 200)


def test_the_file_name_changes_with_the_image(tmp_path):
    red, blue = "https://img.example/red.jpg", "https://img.example/blue.jpg"
    client = _client({red: httpx.Response(200, content=_jpeg(color=(255, 0, 0))),
                      blue: httpx.Response(200, content=_jpeg(color=(0, 0, 255)))})
    a, b = _band(), _band()
    save_band_photo(a, red, tmp_path, client)
    save_band_photo(b, blue, tmp_path, client)
    assert a.image_url != b.image_url


def test_replacing_a_photo_removes_the_old_file(tmp_path):
    first, second = "https://img.example/1.jpg", "https://img.example/2.jpg"
    client = _client({first: httpx.Response(200, content=_jpeg(color=(1, 2, 3))),
                      second: httpx.Response(200, content=_jpeg(color=(200, 100, 50)))})
    band = _band()
    save_band_photo(band, first, tmp_path, client)
    old = tmp_path / band.image_url

    save_band_photo(band, second, tmp_path, client)

    assert not old.exists()
    assert (tmp_path / band.image_url).exists()


@pytest.mark.parametrize("response", [
    httpx.Response(404),
    httpx.Response(200, content=b"<html>not an image</html>"),
])
def test_a_missing_or_undecodable_photo_counts_as_none(tmp_path, response):
    url = "https://img.example/broken.jpg"
    band = _band(image_url=url)  # the edition's remote URL, as the ingest saved it
    assert save_band_photo(band, url, tmp_path, _client({url: response})) is False
    assert band.image_url is None
    assert not any(tmp_path.rglob("*.webp"))


def test_a_failed_replacement_keeps_the_stored_photo(tmp_path):
    good, bad = "https://img.example/good.jpg", "https://img.example/bad.jpg"
    client = _client({good: httpx.Response(200, content=_jpeg())})
    band = _band()
    save_band_photo(band, good, tmp_path, client)
    stored = band.image_url

    assert save_band_photo(band, bad, tmp_path, client) is False
    assert band.image_url == stored and (tmp_path / stored).exists()


def test_stored_paths_and_site_paths():
    assert is_stored("bands/7-abc.webp")
    assert not is_stored("https://img.example/x.jpg")
    assert not is_stored(None)
    assert site_path("bands/7-abc.webp") == "/images/bands/7-abc.webp"
    assert site_path("https://img.example/x.jpg") == "https://img.example/x.jpg"  # not stored yet: as it is
    assert site_path(None) is None


def test_a_photo_is_turned_upright_from_its_exif_orientation(tmp_path):
    """A camera JPEG stored sideways with "rotate 90°" in its EXIF is saved the right way up."""
    url = "https://img.example/sideways.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90° clockwise to display
    buf = io.BytesIO()
    Image.new("RGB", (400, 200), (10, 20, 30)).save(buf, "JPEG", exif=exif)
    band = _band()
    save_band_photo(band, url, tmp_path, _client({url: httpx.Response(200, content=buf.getvalue())}))
    with Image.open(tmp_path / band.image_url) as saved:
        assert saved.size == (200, 400)


def test_an_enormous_image_counts_as_none_without_failing(tmp_path, monkeypatch):
    """Pillow refuses images past its decompression-bomb limit; that's no photo, not an exception."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # so a small test image counts as enormous
    url = "https://img.example/huge.jpg"
    band = _band(image_url=url)
    assert save_band_photo(band, url, tmp_path, _client({url: httpx.Response(200, content=_jpeg(1600, 900))})) is False
    assert band.image_url is None


def test_a_download_over_the_size_limit_counts_as_none(tmp_path, monkeypatch):
    from app.ingestion import band_photos
    monkeypatch.setattr(band_photos, "MAX_DOWNLOAD_BYTES", 1000)
    url = "https://img.example/big.jpg"
    band = _band(image_url=url)
    assert save_band_photo(band, url, tmp_path, _client({url: httpx.Response(200, content=_jpeg())})) is False
    assert band.image_url is None


@pytest.mark.parametrize("response", [httpx.Response(429), httpx.Response(503)])
def test_a_temporary_failure_keeps_the_remote_url_for_the_next_ingest(tmp_path, response):
    """Rate limits and server errors don't mean the photo is gone: keep its URL and try again next time."""
    url = "https://img.example/busy.jpg"
    band = _band(image_url=url)
    assert save_band_photo(band, url, tmp_path, _client({url: response})) is False
    assert band.image_url == url


def test_a_network_error_keeps_the_remote_url(tmp_path):
    url = "https://img.example/down.jpg"
    band = _band(image_url=url)

    def boom(request):
        raise httpx.ConnectError("unreachable", request=request)
    assert save_band_photo(band, url, tmp_path, httpx.Client(transport=httpx.MockTransport(boom))) is False
    assert band.image_url == url


def test_a_photo_that_is_gone_counts_as_none(tmp_path):
    url = "https://img.example/gone.jpg"
    band = _band(image_url=url)
    band.image_credit = {"author": "A", "license": "CC BY 4.0", "license_url": None, "source_url": "https://c/x"}
    assert save_band_photo(band, url, tmp_path, _client({url: httpx.Response(410)})) is False
    assert band.image_url is None
    assert band.image_credit is None  # a credit goes with its photo


def test_an_unexpected_error_for_one_band_does_not_stop_the_others(tmp_path, monkeypatch):
    from app.ingestion import band_photos
    ok, bad = _band(1, "https://img.example/ok.jpg"), _band(2, "https://img.example/bad.jpg")
    real = band_photos.save_band_photo

    def flaky(band, url, images_dir, client=None):
        if band is bad:
            raise PermissionError("disk full")
        return real(band, url, images_dir, _client({url: httpx.Response(200, content=_jpeg())}))
    monkeypatch.setattr(band_photos, "save_band_photo", flaky)

    assert band_photos.save_band_photos([bad, ok], tmp_path) == 1
    assert is_stored(ok.image_url) and bad.image_url == "https://img.example/bad.jpg"


def test_a_commons_photo_that_is_gone_falls_back_to_the_editions(tmp_path, monkeypatch):
    from app.ingestion import band_photos
    commons, edition = "https://upload.wikimedia.org/x-800.jpg", "https://img.example/edition.jpg"
    band = _band(image_url=commons)
    band.image_credit = {"author": "A", "license": "CC BY 4.0", "license_url": None, "source_url": "https://c/x"}
    monkeypatch.setattr(band_photos.httpx, "Client", lambda **kw: _client(
        {commons: httpx.Response(404), edition: httpx.Response(200, content=_jpeg())}))

    assert band_photos.save_band_photos([band], tmp_path, fallbacks={band.name: edition}) == 1
    assert is_stored(band.image_url)
    assert band.image_credit is None  # the edition's photo carries no credit


def test_a_temporary_commons_failure_keeps_it_for_next_time_rather_than_falling_back(tmp_path, monkeypatch):
    from app.ingestion import band_photos
    commons, edition = "https://upload.wikimedia.org/x-800.jpg", "https://img.example/edition.jpg"
    band = _band(image_url=commons)
    band.image_credit = {"author": "A", "license": "CC BY 4.0", "license_url": None, "source_url": "https://c/x"}
    monkeypatch.setattr(band_photos.httpx, "Client", lambda **kw: _client(
        {commons: httpx.Response(503), edition: httpx.Response(200, content=_jpeg())}))

    assert band_photos.save_band_photos([band], tmp_path, fallbacks={band.name: edition}) == 0
    assert band.image_url == commons and band.image_credit is not None
