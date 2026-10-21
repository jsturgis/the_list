"""Tests for saving Show flyers with the data: downloaded, resized to WebP, and stored in the images folder. The
download/resize/store mechanics themselves (EXIF orientation, decompression-bomb guard, size limit, hash naming)
are app.ingestion.image_store's, already covered by tests/test_band_photos.py; these tests cover the Show-specific
shape (no focal point, no credit, gap-filled onto Show.flyer_image_url)."""
from __future__ import annotations

import io

import httpx
from PIL import Image

from app.ingestion.show_flyers import MAX_WIDTH, is_stored, save_show_flyer, save_show_flyers
from app.models.show import Show

_RealClient = httpx.Client


def _client(routes: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request):
        return routes.get(str(request.url), httpx.Response(404))
    return _RealClient(transport=httpx.MockTransport(handler))


def _jpeg(width=1600, height=900, color=(80, 40, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "JPEG")
    return buf.getvalue()


def _show(show_id=9, flyer_image_url=None):
    return Show(id=show_id, flyer_image_url=flyer_image_url)


def test_downloads_resizes_and_stores_a_flyer_as_webp(tmp_path):
    url = "https://venue.example/flyer.jpg"
    show = _show(flyer_image_url=url)

    assert save_show_flyer(show, url, tmp_path, _client({url: httpx.Response(200, content=_jpeg())})) is True

    assert show.flyer_image_url.startswith("shows/9-") and show.flyer_image_url.endswith(".webp")
    with Image.open(tmp_path / show.flyer_image_url) as saved:
        assert saved.format == "WEBP"
        assert saved.size == (MAX_WIDTH, 450)


def test_a_stored_flyer_gets_its_accent_colour(tmp_path):
    # JPEG is lossy, so this allows the colour to drift a couple of levels per channel rather than pinning an
    # exact hex value.
    url = "https://venue.example/flyer.jpg"
    show = _show(flyer_image_url=url)

    save_show_flyer(show, url, tmp_path, _client({url: httpx.Response(200, content=_jpeg(color=(80, 40, 120)))}))

    r, g, b = (int(show.flyer_accent_color[i:i + 2], 16) for i in (1, 3, 5))
    assert abs(r - 80) <= 4 and abs(g - 40) <= 4 and abs(b - 120) <= 4


def test_a_colourless_flyer_gets_no_accent_colour(tmp_path):
    url = "https://venue.example/flyer.jpg"
    show = _show(flyer_image_url=url)

    save_show_flyer(show, url, tmp_path, _client({url: httpx.Response(200, content=_jpeg(color=(128, 128, 128)))}))

    assert show.flyer_accent_color is None


def test_replacing_a_flyer_removes_the_old_file(tmp_path):
    first, second = "https://venue.example/1.jpg", "https://venue.example/2.jpg"
    client = _client({first: httpx.Response(200, content=_jpeg(color=(1, 2, 3))),
                      second: httpx.Response(200, content=_jpeg(color=(200, 100, 50)))})
    show = _show()
    save_show_flyer(show, first, tmp_path, client)
    old = tmp_path / show.flyer_image_url

    save_show_flyer(show, second, tmp_path, client)

    assert not old.exists()
    assert (tmp_path / show.flyer_image_url).exists()


def test_a_missing_flyer_counts_as_none(tmp_path):
    url = "https://venue.example/gone.jpg"
    show = _show(flyer_image_url=url)
    assert save_show_flyer(show, url, tmp_path, _client({url: httpx.Response(404)})) is False
    assert show.flyer_image_url is None


def test_a_temporary_failure_keeps_the_remote_url_for_the_next_ingest(tmp_path):
    url = "https://venue.example/busy.jpg"
    show = _show(flyer_image_url=url)
    assert save_show_flyer(show, url, tmp_path, _client({url: httpx.Response(503)})) is False
    assert show.flyer_image_url == url


def test_a_stored_flyer_has_no_focal_point_or_credit(tmp_path):
    """Unlike a Band photo, a flyer is shown whole: no image_focus/credit fields exist on Show at all."""
    url = "https://venue.example/flyer.jpg"
    show = _show(flyer_image_url=url)
    save_show_flyer(show, url, tmp_path, _client({url: httpx.Response(200, content=_jpeg())}))
    assert not hasattr(show, "image_focus") and not hasattr(show, "image_credit")


def test_save_show_flyers_stores_only_remote_flyers_and_skips_stored_ones(tmp_path, monkeypatch):
    from app.ingestion import show_flyers
    url = "https://venue.example/flyer.jpg"
    remote = _show(1, flyer_image_url=url)
    already_stored = _show(2, flyer_image_url="shows/2-abc.webp")
    none = _show(3)
    monkeypatch.setattr(show_flyers.httpx, "Client", lambda **kw: _client({url: httpx.Response(200, content=_jpeg())}))

    assert save_show_flyers([remote, already_stored, none], tmp_path) == 1
    assert is_stored(remote.flyer_image_url)
    assert already_stored.flyer_image_url == "shows/2-abc.webp"  # untouched


def test_an_unexpected_error_for_one_show_does_not_stop_the_others(tmp_path, monkeypatch):
    from app.ingestion import show_flyers
    url = "https://venue.example/ok.jpg"
    ok, bad = _show(1, url), _show(2, "https://venue.example/bad.jpg")
    real = show_flyers.save_show_flyer

    def flaky(show, u, images_dir, client=None):
        if show is bad:
            raise PermissionError("disk full")
        return real(show, u, images_dir, _client({url: httpx.Response(200, content=_jpeg())}))
    monkeypatch.setattr(show_flyers, "save_show_flyer", flaky)

    assert show_flyers.save_show_flyers([bad, ok], tmp_path) == 1
    assert is_stored(ok.flyer_image_url) and bad.flyer_image_url == "https://venue.example/bad.jpg"
