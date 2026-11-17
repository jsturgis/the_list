"""Tests for saving Show flyers with the data: downloaded, resized to WebP, and stored in the images folder. The
download/resize/store mechanics themselves (EXIF orientation, decompression-bomb guard, size limit, hash naming)
are app.ingestion.image_store's, already covered by tests/test_band_photos.py; these tests cover the Show-specific
shape (no focal point, no credit, gap-filled onto Show.flyer_image_url)."""
from __future__ import annotations

import io

import httpx
from PIL import Image

from datetime import date

from app.ingestion.show_flyers import MAX_WIDTH, is_stored, prune_show_flyers, save_show_flyer, save_show_flyers

from app.models.show import Show, ShowStatus
from app.models.venue import Region, Venue

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
    monkeypatch.setattr(show_flyers, "guarded_client", lambda **kw: _client({url: httpx.Response(200, content=_jpeg())}))

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


def test_a_gone_flyer_is_remembered_so_the_calendar_does_not_hand_it_back(tmp_path):
    url = "https://venue.example/gone.jpg"
    show = _show(flyer_image_url=url)

    assert save_show_flyer(show, url, tmp_path, _client({})) is False   # 404

    assert (show.flyer_image_url, show.flyer_gone_url) == (None, url)


def test_a_flyer_that_fails_for_now_is_not_remembered_as_gone(tmp_path):
    url = "https://venue.example/busy.jpg"
    show = _show(flyer_image_url=url)

    save_show_flyer(show, url, tmp_path, _client({url: httpx.Response(503)}))

    assert (show.flyer_image_url, show.flyer_gone_url) == (url, None)


def test_pruning_deletes_the_flyers_the_site_no_longer_shows(db, tmp_path):
    """The export has only Shows from today on that aren't Past (app/export.py), so their flyers are dead weight
    on the data branch, as is any file no Show points at."""
    today = date(2026, 11, 17)
    venue = Venue(name="The Chapel", city="San Francisco", region=Region.sf)
    db.add(venue)
    db.flush()
    folder = tmp_path / "shows"
    folder.mkdir()

    def show(day, name, status=ShowStatus.upcoming):
        (folder / name).write_bytes(b"webp")
        s = Show(date=day, venue_id=venue.id, status=status, flyer_image_url=f"shows/{name}")
        db.add(s)
        return s

    upcoming = show(today, "1-a.webp")
    yesterday = show(date(2026, 11, 16), "2-b.webp")
    marked_past = show(today, "3-c.webp", status=ShowStatus.past)
    (folder / "4-orphan.webp").write_bytes(b"webp")
    db.flush()

    assert prune_show_flyers(db, tmp_path, today) == 3

    assert sorted(p.name for p in folder.iterdir()) == ["1-a.webp"]
    assert upcoming.flyer_image_url == "shows/1-a.webp"
    assert yesterday.flyer_image_url is None and marked_past.flyer_image_url is None
