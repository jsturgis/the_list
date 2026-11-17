"""The Admin page's ingest jobs (app/ingest_jobs.py, `python -m app.cli ingest-jobs`): each job's progress and outcome
recorded in Supabase, a failing job not stopping the rest, and `ingest_shows` reporting its phases."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app import ingest_jobs
from app.alerts import SupabaseError
from app.cli import main
from app.ingest_jobs import Job, parse_specs, run_jobs
from app.ingestion.ticketweb import EventError, UnreadablePage, event_show
from app.ingestion.upsert import upsert_shows
from app.models.show import Show
from app.scheduler import ingest_shows

_URL = "https://www.ticketweb.com/event/teenage-bottlerocket-w-brendan-kelly-moes-alley-tickets/14446334"
_PAGE = (Path(__file__).parent / "fixtures" / "ticketweb_event.html").read_text()
_TODAY = date(2026, 11, 17)
_TICKETWEB = Job("job-1", 11, "ticketweb", _URL, None)
_SCREENSHOT = Job("job-2", 12, "screenshot", None, "user/shot.png")
_FIELDS = {"performers": ["Wet Leg"], "venue": "The Chapel", "city": "San Francisco", "date": "Dec 5",
           "doors_time": "8pm", "show_time": None, "price": "$25", "age": None, "status": None}


def test_reads_the_workflows_jobs():
    assert parse_specs("a:1, b:22,") == [("a", 1), ("b", 22)]
    with pytest.raises(ValueError):
        parse_specs("a")


@pytest.fixture
def supabase():
    """Supabase's side of the jobs: every update and finish, in order."""
    calls = []
    with patch("app.ingest_jobs.update_jobs", side_effect=lambda ids, **f: calls.append(("update", ids, f))), \
         patch("app.ingest_jobs.finish_job",
               side_effect=lambda job, status, **f: calls.append(("finish", job.id, status, f))), \
         patch("app.ingest_jobs.download_screenshot", return_value=b"png"):
        yield calls


def _stored(db):
    """`ingest_shows` without the services, reporting one phase: it stores the Shows and commits."""
    async def ingest(_db, shows_data, on_phase=None, **kwargs):
        on_phase("saving", None)
        shows = upsert_shows(db, shows_data)
        db.commit()
        return shows
    return ingest


@patch("app.ingest_jobs.fetch_event", return_value=event_show(_PAGE, _URL))
def test_a_ticketweb_job_is_ingested_and_its_progress_recorded(fetch, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        added = run_jobs(db, [_TICKETWEB], _TODAY, "https://github.com/run/1")

    assert added == ["job-1"]
    show = db.query(Show).one()
    assert supabase == [
        ("update", ["job-1"], {"status": "running", "phase": "dispatched", "detail": None, "message": None,
                               "workflow_run_url": "https://github.com/run/1"}),
        ("update", ["job-1"], {"phase": "fetching_page", "detail": _URL}),
        ("update", ["job-1"], {"phase": "saving", "detail": None}),
        ("finish", "job-1", "added", {"message": "Added Teenage Bottlerocket, Brendan Kelly at Moe's Alley, Santa Cruz "
                                                 "on Thu Jan 21, 2027", "show_id": show.id, "extracted": None}),
    ]


@patch("app.ingestion.screenshot.read_fields", return_value=_FIELDS)
def test_a_screenshot_job_is_read_by_the_model_and_ingested(read, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        added = run_jobs(db, [_SCREENSHOT], _TODAY)

    assert added == ["job-2"]
    read.assert_called_once_with(b"png")
    assert supabase[1] == ("update", ["job-2"], {"phase": "reading_screenshot",
                                                 "detail": "Reading it with qwen2.5vl:3b"})
    _, _, status, finished = supabase[-1]
    assert status == "added"
    assert finished["extracted"] == _FIELDS
    assert db.query(Show).one().source == "screenshot"


@patch("app.ingest_jobs.fetch_event", return_value=event_show(_PAGE, _URL))
def test_a_show_the_list_already_has_only_adds_its_ticket_link(fetch, db, supabase):
    upsert_shows(db, [{**event_show(_PAGE, _URL), "source": "list", "ticket_provider": None, "ticket_url": None}])
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        run_jobs(db, [_TICKETWEB], _TODAY)

    _, _, status, finished = supabase[-1]
    assert status == "added"
    assert finished["message"].startswith("The List already has it (Teenage Bottlerocket")
    assert finished["message"].endswith("; added its ticket link")


@patch("app.ingestion.screenshot.read_fields", return_value={**_FIELDS, "city": "Portland"})
@patch("app.ingest_jobs.fetch_event", side_effect=EventError("couldn't fetch it: 506"))
def test_a_failing_job_is_recorded_and_doesnt_stop_the_others(fetch, read, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        added = run_jobs(db, [_TICKETWEB, _SCREENSHOT], _TODAY)

    assert added == []
    finishes = [c for c in supabase if c[0] == "finish"]
    assert finishes[0] == ("finish", "job-1", "failed", {"message": "couldn't fetch it: 506", "extracted": None})
    assert finishes[1][2] == "failed"
    assert "Portland" in finishes[1][3]["message"]
    assert finishes[1][3]["extracted"]["city"] == "Portland"   # what the model read, to see what went wrong


@patch("app.ingest_jobs.fetch_event", return_value=event_show(_PAGE, _URL))
def test_an_unexpected_error_fails_the_job(fetch, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=RuntimeError("database is locked")):
        assert run_jobs(db, [_TICKETWEB], _TODAY) == []

    assert supabase[-1] == ("finish", "job-1", "failed", {"message": "RuntimeError: database is locked",
                                                          "extracted": None})


@patch("app.ingest_jobs.fetch_event", side_effect=UnreadablePage("couldn't fetch it: 530 Unknown Error"))
def test_a_link_whose_page_cant_be_read_says_to_add_a_screenshot(fetch, db, supabase):
    run_jobs(db, [Job("job-5", 15, "page", "https://www.bandsintown.com/e/1", None)], _TODAY)

    assert supabase[1] == ("update", ["job-5"], {"phase": "fetching_page", "detail": "https://www.bandsintown.com/e/1"})
    assert supabase[-1] == ("finish", "job-5", "failed", {
        "message": "couldn't fetch it: 530 Unknown Error. Take a screenshot of the event and add that instead.",
        "extracted": None})


@patch("app.ingest_jobs.fetch_event")
def test_a_job_an_earlier_run_finished_is_skipped(fetch, db, supabase):
    assert run_jobs(db, [Job("job-1", 11, "ticketweb", _URL, None, "added")], _TODAY) == []
    fetch.assert_not_called()
    assert supabase == []


@patch("app.ingest_jobs.fetch_event", return_value=event_show(_PAGE, _URL))
def test_losing_supabase_stops_the_run(fetch, db):
    """The jobs stay on the queue and are handed out again."""
    with patch("app.ingest_jobs.update_jobs", side_effect=SupabaseError("down")):
        with pytest.raises(SupabaseError):
            run_jobs(db, [_TICKETWEB], _TODAY)


# ── Supabase requests ─────────────────────────────────────────────────────────

@pytest.fixture
def requests(monkeypatch):
    monkeypatch.setattr("app.ingest_jobs.settings.supabase_url", "https://x.supabase.co/")
    monkeypatch.setattr("app.ingest_jobs.settings.supabase_service_role_key", "sb_secret_x")
    sent = []

    def request(method, url, **kwargs):
        sent.append((method, url, kwargs))
        body = [{"id": "job-1", "provider": "ticketweb", "url": _URL, "screenshot_path": None}]
        return httpx.Response(200, json=body, request=httpx.Request(method, url))
    with patch("app.ingest_jobs.httpx.request", side_effect=request):
        yield sent


def test_fetches_the_jobs_it_was_given(requests):
    jobs = ingest_jobs.fetch_jobs([("job-1", 11), ("gone", 12)])

    assert jobs == [Job("job-1", 11, "ticketweb", _URL, None, "queued")]
    method, url, kwargs = requests[0]
    assert (method, url) == ("GET", "https://x.supabase.co/rest/v1/ingest_jobs")
    assert kwargs["params"]["id"] == "in.(job-1,gone)"
    assert kwargs["headers"]["apikey"] == "sb_secret_x"


def test_finishing_a_job_takes_it_off_the_queue(requests):
    ingest_jobs.finish_job(_TICKETWEB, "added", message="Added it", show_id=7)

    method, url, kwargs = requests[0]
    assert (method, url) == ("POST", "https://x.supabase.co/rest/v1/rpc/finish_ingest_job")
    assert kwargs["json"] == {"job_id": "job-1", "msg_id": 11, "new_status": "added", "new_message": "Added it",
                              "new_show_id": 7, "new_extracted": None}


def test_needs_supabase(monkeypatch):
    monkeypatch.setattr("app.ingest_jobs.settings.supabase_url", "")
    with pytest.raises(SupabaseError):
        ingest_jobs.update_jobs(["job-1"], phase="live")


# ── the commands ──────────────────────────────────────────────────────────────

@pytest.fixture
def keys_work():
    with patch("app.ingestion.lastfm.lastfm_key_problem", return_value=None), \
         patch("app.ingestion.discogs.discogs_key_problem", return_value=None):
        yield


@patch("app.cli.SessionLocal")
@patch("app.ingest_jobs.run_jobs", return_value=["job-1"])
@patch("app.ingest_jobs.fetch_jobs", return_value=[_TICKETWEB, _SCREENSHOT])
def test_ingest_jobs_tells_the_workflow_which_jobs_added_a_show(fetch, run, session, db, keys_work, tmp_path,
                                                                 monkeypatch, capsys):
    session.return_value = db
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_RUN_ID", "99")
    monkeypatch.setenv("GITHUB_REPOSITORY", "jsturgis/the_list")

    main(["ingest-jobs", "--jobs", "job-1:11,job-2:12"])

    fetch.assert_called_once_with([("job-1", 11), ("job-2", 12)])
    assert run.call_args.args[3] == "https://github.com/jsturgis/the_list/actions/runs/99"
    assert output.read_text() == "added=job-1\n"
    assert "1 of 2 added" in capsys.readouterr().out


@patch("app.ingest_jobs.fetch_jobs")
@patch("app.ingestion.lastfm.lastfm_key_problem", return_value="LASTFM_API_KEY isn't set")
@patch("app.ingestion.discogs.discogs_key_problem", return_value=None)
def test_ingest_jobs_needs_the_service_keys(discogs, lastfm, fetch):
    with pytest.raises(SystemExit, match="LASTFM_API_KEY"):
        main(["ingest-jobs", "--jobs", "job-1:11"])
    fetch.assert_not_called()


@patch("app.ingest_jobs.fetch_jobs", side_effect=SupabaseError("Supabase GET failed"))
def test_ingest_jobs_exits_non_zero_without_supabase(fetch, keys_work):
    with pytest.raises(SystemExit, match="Supabase GET failed"):
        main(["ingest-jobs", "--jobs", "job-1:11"])


@patch("app.ingest_jobs.update_jobs")
def test_ingest_jobs_phase_records_how_far_they_have_got(update, capsys):
    main(["ingest-jobs-phase", "--jobs", "job-1,job-2", "--phase", "deploying", "--detail", "https://run/2"])
    update.assert_called_once_with(["job-1", "job-2"], phase="deploying", detail="https://run/2")


@patch("app.ingest_jobs.update_jobs")
@patch("app.ingest_jobs.unfinished", return_value=["job-2"])
def test_ingest_jobs_phase_can_fail_only_the_unfinished_jobs(unfinished, update):
    main(["ingest-jobs-phase", "--jobs", "job-1,job-2", "--status", "failed", "--message", "the run broke off",
          "--unfinished-only"])
    update.assert_called_once_with(["job-2"], status="failed", message="the run broke off")


# ── ingest_shows' phases ──────────────────────────────────────────────────────

def _venue_data(name, city, street=None, use_llm=True):
    return {"address": f"{street}, {city}, CA 95065, USA", "google_place_id": f"ChIJ-{name}", "city": city}


@pytest.fixture
def services():
    with patch("app.scheduler._enrich_venue", side_effect=_venue_data), \
         patch("app.scheduler._enrich_band", return_value={"genres": ["punk"], "mb_genres": True}), \
         patch("app.scheduler.split_joint_name", side_effect=lambda name: [name]), \
         patch("app.scheduler.save_band_photos", return_value=0), \
         patch("app.scheduler.save_venue_photos", return_value=0), \
         patch("app.scheduler.check_image_urls", side_effect=lambda urls: {u: u for u in urls}), \
         patch("app.scheduler.commons_photo", return_value=None), \
         patch("app.scheduler.discogs_artist", return_value=None), \
         patch("app.scheduler.batch_embed_and_index", new_callable=AsyncMock):
        yield


async def test_ingest_shows_reports_each_phase_as_it_starts(db, services):
    """("photos" too, when the services found any to check.)"""
    phases = []
    await ingest_shows(db, [event_show(_PAGE, _URL)], on_phase=lambda phase, detail: phases.append((phase, detail)))

    assert phases == [
        ("venue", "Moe's Alley"),
        ("venue", "Looking up Moe's Alley on Google Places"),
        ("bands", None),
        ("bands", "Looking up Band 1 of 2: Teenage Bottlerocket"),
        ("bands", "Looking up Band 2 of 2: Brendan Kelly"),
        ("saving", None),
        ("embedding", None),
    ]


async def test_a_phase_that_cant_be_reported_doesnt_fail_the_ingest(db, services):
    def broken(phase, detail):
        raise SupabaseError("down")

    (show,) = await ingest_shows(db, [event_show(_PAGE, _URL)], on_phase=broken)
    assert show.source == "ticketweb"
