"""Tests for saving Band photos with the data: downloaded, resized to WebP, and stored in the images folder."""
from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.ingestion.band_photos import MAX_WIDTH, is_stored, save_band_photo, site_path
from app.ingestion.photo_focus import DEFAULT
from app.models.band import Band

FACE = Path(__file__).parent / "fixtures" / "face.jpg"  # NASA's astronaut photo, public domain (test_photo_focus.py)


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

    assert band_photos.save_band_photos([band], tmp_path, fallbacks={band.name: [{"url": edition, "credit": None}]}) == 1
    assert is_stored(band.image_url)
    assert band.image_credit is None  # the edition's photo carries no credit


def test_a_temporary_commons_failure_keeps_it_for_next_time_rather_than_falling_back(tmp_path, monkeypatch):
    from app.ingestion import band_photos
    commons, edition = "https://upload.wikimedia.org/x-800.jpg", "https://img.example/edition.jpg"
    band = _band(image_url=commons)
    band.image_credit = {"author": "A", "license": "CC BY 4.0", "license_url": None, "source_url": "https://c/x"}
    monkeypatch.setattr(band_photos.httpx, "Client", lambda **kw: _client(
        {commons: httpx.Response(503), edition: httpx.Response(200, content=_jpeg())}))

    assert band_photos.save_band_photos([band], tmp_path, fallbacks={band.name: [{"url": edition, "credit": None}]}) == 0
    assert band.image_url == commons and band.image_credit is not None


def test_a_gone_photo_falls_back_down_the_list_with_each_ones_credit(tmp_path, monkeypatch):
    """Commons gone, then Discogs gone too: the edition's photo, with no credit."""
    from app.ingestion import band_photos
    commons, disc, edition = "https://upload.wikimedia.org/x.jpg", "https://i.discogs.com/x.jpg", "https://img.example/e.jpg"
    discogs_credit = {"source": "Discogs", "author": None, "license": None, "license_url": None,
                      "source_url": "https://www.discogs.com/artist/1"}
    band = _band(image_url=commons)
    band.image_credit = {"source": "Wikimedia Commons", "author": "A", "license": "CC BY 4.0", "license_url": None,
                         "source_url": "https://c/x"}
    routes = {commons: httpx.Response(404), disc: httpx.Response(200, content=_jpeg())}
    monkeypatch.setattr(band_photos.httpx, "Client", lambda **kw: _client(routes))

    fallbacks = {band.name: [{"url": disc, "credit": discogs_credit}, {"url": edition, "credit": None}]}
    assert band_photos.save_band_photos([band], tmp_path, fallbacks=fallbacks) == 1
    assert is_stored(band.image_url) and band.image_credit == discogs_credit   # Discogs', credited

    band2 = _band(3, image_url=commons)
    routes[disc] = httpx.Response(410)
    routes[edition] = httpx.Response(200, content=_jpeg(color=(9, 9, 9)))
    assert band_photos.save_band_photos([band2], tmp_path, fallbacks={band2.name: fallbacks[band.name]}) == 1
    assert is_stored(band2.image_url) and band2.image_credit is None             # the edition's, uncredited


# The focal point (app/ingestion/photo_focus.py) goes with the photo

def _face_photo(left: int) -> bytes:
    """A wide photo with a real face (tests/fixtures/face.jpg) pasted `left` pixels in."""
    canvas = Image.new("RGB", (1600, 900), (40, 40, 60))
    with Image.open(FACE) as face:
        canvas.paste(face.convert("RGB").resize((320, 320)), (left, 80))
    buf = io.BytesIO()
    canvas.save(buf, "JPEG")
    return buf.getvalue()


def test_a_stored_photo_gets_its_focal_point(tmp_path):
    url = "https://img.example/singer.jpg"
    band = _band(image_url=url)
    save_band_photo(band, url, tmp_path, _client({url: httpx.Response(200, content=_face_photo(0))}))
    assert band.image_focus["x"] < 20 and band.image_focus["y"] < 25   # the face, top left

    plain = _band(8)
    save_band_photo(plain, url, tmp_path, _client({url: httpx.Response(200, content=_jpeg())}))
    assert plain.image_focus == DEFAULT                                 # no face


def test_a_new_photo_brings_its_own_focal_point(tmp_path):
    left, right = "https://img.example/left.jpg", "https://img.example/right.jpg"
    client = _client({left: httpx.Response(200, content=_face_photo(0)),
                      right: httpx.Response(200, content=_face_photo(1280))})
    band = _band()
    save_band_photo(band, left, tmp_path, client)
    assert band.image_focus["x"] < 20
    save_band_photo(band, right, tmp_path, client)
    assert band.image_focus["x"] > 80


def test_a_photo_that_goes_takes_its_focal_point_with_it(tmp_path):
    url = "https://img.example/gone.jpg"
    band = Band(id=7, name="Redwood Sirens", image_url=url, image_focus={"x": 10.0, "y": 20.0})
    save_band_photo(band, url, tmp_path, _client({url: httpx.Response(404)}))
    assert band.image_url is None and band.image_focus is None


def test_a_failed_focal_point_doesnt_lose_the_photo(tmp_path, monkeypatch):
    from app.ingestion import band_photos
    monkeypatch.setattr(band_photos, "photo_focus_of", lambda data: (_ for _ in ()).throw(RuntimeError("cv2")))
    url = "https://img.example/x.jpg"
    band = _band()
    assert save_band_photo(band, url, tmp_path, _client({url: httpx.Response(200, content=_jpeg())})) is True
    assert is_stored(band.image_url) and band.image_focus is None   # the photo-focus command tries again


def test_changing_or_clearing_a_saved_bands_photo_clears_its_focal_point(db):
    band = Band(name="Saved", genres=[], image_url="bands/1-a.webp", image_focus={"x": 10.0, "y": 20.0})
    db.add(band)
    db.commit()
    band.image_url = "bands/1-a.webp"                      # the same photo: kept
    assert band.image_focus == {"x": 10.0, "y": 20.0}
    db.commit()
    band.image_url = "bands/1-b.webp"                      # after a commit, not loaded yet: still noticed
    assert band.image_focus is None
    band.image_focus = {"x": 1.0, "y": 2.0}
    db.commit()
    band.image_url = None
    db.commit()
    db.refresh(band)
    assert band.image_focus is None
