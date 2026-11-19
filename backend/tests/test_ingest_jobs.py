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
from app.ingest_jobs import Job, Saved, finish_saved, parse_specs, run_jobs
from app.ingestion.screenshot import ScreenshotError
from app.ingestion.ticketweb import EventError, NoEventDetails, UnreadablePage, event_show
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


def _run(db, jobs, today=_TODAY, run_url=None):
    """run_jobs, then finish the jobs that added Shows, as the workflow does once they're pushed; their ids."""
    saved = run_jobs(db, jobs, today, run_url)
    finish_saved(saved)
    return [s.job_id for s in saved]


def _stored(db):
    """`ingest_shows` without the services, reporting one phase: it stores the Shows and commits."""
    async def ingest(_db, shows_data, on_phase=None, **kwargs):
        on_phase("saving", None)
        shows = upsert_shows(db, shows_data)
        db.commit()
        return shows
    return ingest


@patch("app.ingest_jobs.fetch_events", return_value=[event_show(_PAGE, _URL)])
def test_a_ticketweb_job_is_ingested_and_its_progress_recorded(fetch, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        added = _run(db, [_TICKETWEB], _TODAY, "https://github.com/run/1")

    assert added == ["job-1"]
    show = db.query(Show).one()
    assert supabase == [
        ("update", ["job-1"], {"status": "running", "phase": "dispatched", "detail": None, "message": None,
                               "workflow_run_url": "https://github.com/run/1"}),
        ("update", ["job-1"], {"phase": "fetching_page", "detail": _URL}),
        ("update", ["job-1"], {"phase": "saving", "detail": None}),
        ("finish", "job-1", "added", {"message": "Added Teenage Bottlerocket, Brendan Kelly at Moe's Alley, Santa Cruz "
                                                 "on Thu Jan 21, 2027", "show_id": show.id, "extracted": None,
                                     "shows_query": None}),
    ]


@patch("app.ingestion.screenshot.read_fields", return_value=_FIELDS)
def test_a_screenshot_is_read_then_waits_for_review_adding_nothing(read, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)) as ingest:
        added = _run(db, [_SCREENSHOT], _TODAY)

    assert added == []
    read.assert_called_once_with(b"png")
    assert supabase[1] == ("update", ["job-2"], {"phase": "reading_screenshot",
                                                 "detail": "Reading it with qwen2.5vl:3b"})
    assert supabase[-1] == ("finish", "job-2", "review", {"message": "Check what was read, then approve it",
                                                          "extracted": _FIELDS})
    ingest.assert_not_called()
    assert db.query(Show).count() == 0


@patch("app.ingestion.screenshot.read_fields", return_value={**_FIELDS, "date": None})
def test_a_screenshot_that_cant_be_added_as_read_goes_to_review_with_why(read, db, supabase):
    """The admin can put the date in."""
    _run(db, [_SCREENSHOT], _TODAY)

    assert supabase[-1] == ("finish", "job-2", "review", {"message": "Check what was read: no date on the screenshot",
                                                          "extracted": {**_FIELDS, "date": None}})


@patch("app.ingestion.screenshot.read_fields", side_effect=ScreenshotError("couldn't read the screenshot: 400"))
def test_a_screenshot_the_model_cant_read_fails(read, db, supabase):
    _run(db, [_SCREENSHOT], _TODAY)

    assert supabase[-1][:3] == ("finish", "job-2", "failed")


_APPROVED = Job("job-2", 13, "screenshot", None, "user/shot.png", "queued", {**_FIELDS, "performers": ["Wet Leg", "Idles"]},
                approved=True)


@patch("app.ingestion.screenshot.read_fields")
def test_an_approved_screenshot_is_added_as_reviewed_without_asking_the_model_again(read, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        added = _run(db, [_APPROVED], _TODAY)

    assert added == ["job-2"]
    read.assert_not_called()
    assert supabase[1] == ("update", ["job-2"], {"phase": "review", "detail": "Using the details as reviewed"})
    show = db.query(Show).one()
    assert (show.source, [a.band.name for a in show.acts]) == ("screenshot", ["Wet Leg", "Idles"])
    assert supabase[-1][:3] == ("finish", "job-2", "added")


def test_an_approved_screenshot_that_still_cant_be_added_goes_back_to_review(db, supabase):
    job = Job("job-2", 13, "screenshot", None, "user/shot.png", "queued", {**_FIELDS, "city": "Portland"}, approved=True)
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)) as ingest:
        assert _run(db, [job], _TODAY) == []

    ingest.assert_not_called()
    _, _, status, finished = supabase[-1]
    assert status == "review"
    assert finished["message"] == "Check what was read: The Chapel is in Portland, not a Bay Area city we know"


@patch("app.ingest_jobs.fetch_events", return_value=[event_show(_PAGE, _URL)])
def test_a_show_the_list_already_has_only_adds_its_ticket_link(fetch, db, supabase):
    upsert_shows(db, [{**event_show(_PAGE, _URL), "source": "list", "ticket_provider": None, "ticket_url": None}])
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        _run(db, [_TICKETWEB], _TODAY)

    _, _, status, finished = supabase[-1]
    assert status == "added"
    assert finished["message"].startswith("The List already has it (Teenage Bottlerocket")
    assert finished["message"].endswith("; added its ticket link")


@patch("app.ingestion.screenshot.read_fields", return_value={**_FIELDS, "city": "Portland"})
@patch("app.ingest_jobs.fetch_events", side_effect=EventError("couldn't fetch it: 506"))
def test_a_failing_job_is_recorded_and_doesnt_stop_the_others(fetch, read, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        added = _run(db, [_TICKETWEB, _SCREENSHOT], _TODAY)

    assert added == []
    finishes = [c for c in supabase if c[0] == "finish"]
    assert finishes[0] == ("finish", "job-1", "failed", {"message": "couldn't fetch it: 506", "extracted": None})
    assert finishes[1][2] == "review"   # the screenshot, read, goes on to be reviewed
    assert "Portland" in finishes[1][3]["message"]
    assert finishes[1][3]["extracted"]["city"] == "Portland"   # what the model read, to see what went wrong


@patch("app.ingest_jobs.fetch_events", return_value=[event_show(_PAGE, _URL)])
def test_an_unexpected_error_fails_the_job(fetch, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=RuntimeError("database is locked")):
        assert _run(db, [_TICKETWEB], _TODAY) == []

    assert supabase[-1] == ("finish", "job-1", "failed", {"message": "RuntimeError: database is locked",
                                                          "extracted": None})


@patch("app.ingest_jobs.fetch_events", side_effect=UnreadablePage("couldn't fetch it: 530 Unknown Error"))
def test_a_link_whose_page_cant_be_read_says_to_add_a_screenshot(fetch, db, supabase):
    _run(db, [Job("job-5", 15, "page", "https://www.bandsintown.com/e/1", None)], _TODAY)

    assert supabase[1] == ("update", ["job-5"], {"phase": "fetching_page", "detail": "https://www.bandsintown.com/e/1"})
    assert supabase[-1] == ("finish", "job-5", "failed", {
        "message": "couldn't fetch it: 530 Unknown Error. Take a screenshot of the event and add that instead.",
        "extracted": None})


_UCT = "https://www.theuctheatre.org/shows/victor-wooten-10-dec"
_UCT_JOB = Job("job-6", 16, "page", _UCT, None)
_UCT_FIELDS = {"performers": ["Victor Wooten and The Wooten Brothers"], "venue": "The UC Theatre", "city": "Berkeley",
               "date": "December 10, 2026", "doors_time": "7:00 pm", "show_time": "8:00 pm", "price": "$35.00",
               "age": "All Ages", "status": None}


@patch("app.ingest_jobs.read_page_fields", return_value=_UCT_FIELDS)
@patch("app.ingest_jobs.fetch_events", side_effect=NoEventDetails(f"{_UCT} has no event details on it", "<html>", _UCT))
def test_a_page_with_no_schema_org_event_is_read_by_the_llm_then_waits_for_review(fetch, read, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)) as ingest:
        assert _run(db, [_UCT_JOB], _TODAY) == []

    read.assert_called_once_with("<html>", _UCT, _TODAY)
    assert ("update", ["job-6"], {"phase": "reading_page", "detail": "Reading it with Claude Haiku"}) in supabase
    assert supabase[-1] == ("finish", "job-6", "review", {"message": "Check what was read, then approve it",
                                                          "extracted": _UCT_FIELDS})
    ingest.assert_not_called()


@patch("app.ingest_jobs.read_page_fields", return_value={**_UCT_FIELDS, "venue": None})
@patch("app.ingest_jobs.fetch_events", side_effect=NoEventDetails(f"{_UCT} has no event details on it", "<html>", _UCT))
def test_a_page_read_that_cant_be_added_as_read_goes_to_review_with_why(fetch, read, db, supabase):
    _run(db, [_UCT_JOB], _TODAY)

    _, _, status, finished = supabase[-1]
    assert (status, finished["message"]) == ("review", "Check what was read: no venue on the page")


@patch("app.ingest_jobs.read_page_fields", side_effect=UnreadablePage(f"{_UCT} has no event on it that Claude Haiku could read"))
@patch("app.ingest_jobs.fetch_events", side_effect=NoEventDetails(f"{_UCT} has no event details on it", "<html>", _UCT))
def test_a_page_the_llm_finds_no_event_on_asks_for_a_screenshot(fetch, read, db, supabase):
    _run(db, [_UCT_JOB], _TODAY)

    assert supabase[-1] == ("finish", "job-6", "failed", {
        "message": f"{_UCT} has no event on it that Claude Haiku could read. "
                   "Take a screenshot of the event and add that instead.",
        "extracted": None})


@patch("app.ingest_jobs.read_page_fields")
@patch("app.ingest_jobs.fetch_events", side_effect=NoEventDetails("no event details on it (the site may have turned "
                                                                  "the request away)", "<challenge>", _URL))
def test_a_ticketweb_page_with_no_event_isnt_read_by_the_llm(fetch, read, db, supabase):
    """TicketWeb always has its JSON-LD: without it, the page is a challenge page."""
    _run(db, [_TICKETWEB], _TODAY)

    read.assert_not_called()
    _, _, status, finished = supabase[-1]
    assert status == "failed" and "the site may have turned the request away" in finished["message"]


def test_an_approved_page_read_that_still_cant_be_added_goes_back_to_review(db, supabase):
    job = Job("job-6", 17, "page", _UCT, None, "queued", {**_UCT_FIELDS, "city": "Portland"}, approved=True)
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)) as ingest:
        assert _run(db, [job], _TODAY) == []

    ingest.assert_not_called()
    _, _, status, finished = supabase[-1]
    assert (status, finished["message"]) == (
        "review", "Check what was read: The UC Theatre is in Portland, not a Bay Area city we know")


@patch("app.ingest_jobs.read_page_fields")
@patch("app.ingest_jobs.fetch_events")
def test_an_approved_page_read_is_added_with_the_page_as_its_ticket_link(fetch, read, db, supabase):
    job = Job("job-6", 17, "page", _UCT, None, "queued", _UCT_FIELDS, approved=True)
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        assert _run(db, [job], _TODAY) == ["job-6"]

    fetch.assert_not_called()
    read.assert_not_called()
    show = db.query(Show).one()
    assert (show.source, show.date, show.ticket_url, show.ticket_provider) == (
        "page", date(2026, 12, 10), _UCT, "theuctheatre.org")
    assert [a.band.name for a in show.acts] == ["Victor Wooten and The Wooten Brothers"]


def _elsewhere(data: dict, venue: str, city: str, day: int) -> dict:
    return {**data, "venue_name": venue, "city": city, "address": None, "date": date(2027, 1, day),
            "ticket_url": f"{_URL}/{day}", "raw_text": f"Teenage Bottlerocket at {venue}, {city}"}


_ARTIST = Job("job-6", 16, "page", "https://www.bandsintown.com/a/9536-teenage-bottlerocket", None)


def test_a_page_of_several_bay_area_shows_adds_each(db, supabase):
    first = event_show(_PAGE, _URL)
    second = _elsewhere(first, "Berkeley Brewing Company", "Berkeley", 24)
    with patch("app.ingest_jobs.fetch_events", return_value=[first, second]), \
         patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        added = _run(db, [_ARTIST], _TODAY)

    assert added == ["job-6"]
    shows = db.query(Show).order_by(Show.date).all()
    assert [s.venue.name for s in shows] == ["Moe's Alley", "Berkeley Brewing Company"]
    assert ("update", ["job-6"], {"phase": "saving", "detail": "Show 2 of 2"}) in supabase   # which Show it's on
    _, _, status, finished = supabase[-1]
    assert status == "added"
    assert finished["show_id"] == shows[0].id
    # The Admin page links to the Shows list, filtered to them: the Band they share, over their dates.
    band_id = next(a.band_id for a in shows[0].acts if a.position == min(x.position for x in shows[0].acts))
    assert finished["shows_query"] == f"bandId={band_id}&fromDate=2027-01-21&toDate=2027-01-24"
    assert finished["message"] == (
        "Added 2 Shows: Teenage Bottlerocket, Brendan Kelly at Moe's Alley, Santa Cruz on Thu Jan 21, 2027; "
        "Teenage Bottlerocket, Brendan Kelly at Berkeley Brewing Company, Berkeley on Sun Jan 24, 2027")


def test_a_show_that_cant_be_added_doesnt_lose_the_others_on_its_page(db, supabase):
    first = event_show(_PAGE, _URL)
    second = _elsewhere(first, "Berkeley Brewing Company", "Berkeley", 24)
    ingest = _stored(db)

    async def fails_for_berkeley(_db, shows_data, on_phase=None, **kwargs):
        if shows_data[0]["city"] == "Berkeley":
            raise RuntimeError("geocoding failed")
        return await ingest(_db, shows_data, on_phase=on_phase)

    with patch("app.ingest_jobs.fetch_events", return_value=[second, first]), \
         patch("app.scheduler.ingest_shows", side_effect=fails_for_berkeley):
        assert _run(db, [_ARTIST], _TODAY) == ["job-6"]

    assert [s.venue.name for s in db.query(Show).all()] == ["Moe's Alley"]
    _, _, status, finished = supabase[-1]
    assert status == "added"
    assert finished["message"].startswith("Added 1 Show: Teenage Bottlerocket, Brendan Kelly at Moe's Alley")
    assert finished["message"].endswith(
        ". Couldn't add 1: Teenage Bottlerocket at Berkeley Brewing Company, Berkeley (geocoding failed)")


def test_a_job_with_one_show_has_no_shows_query(db, supabase):
    with patch("app.ingest_jobs.fetch_events", return_value=[event_show(_PAGE, _URL)]), \
         patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        _run(db, [_TICKETWEB], _TODAY)
    assert supabase[-1][3]["shows_query"] is None   # its link is the Show's own page


def test_shows_with_no_band_in_common_are_picked_out_by_their_venue(db):
    first = event_show(_PAGE, _URL)
    other = {**first, "date": date(2027, 2, 3), "bands": ["Wet Leg"], "act_notes": [None],
             "band_enrichment": [("Wet Leg", {"genres": []})], "ticket_url": f"{_URL}/2"}
    shows = upsert_shows(db, [first, other])
    assert ingest_jobs.shows_query(shows) == f"venueId={shows[0].venue_id}&fromDate=2027-01-21&toDate=2027-02-03"


def test_shows_with_nothing_in_common_have_no_shows_query(db):
    first = event_show(_PAGE, _URL)
    other = {**_elsewhere(first, "924 Gilman", "Berkeley", 30), "bands": ["Wet Leg"], "act_notes": [None],
             "band_enrichment": [("Wet Leg", {"genres": []})]}
    assert ingest_jobs.shows_query(upsert_shows(db, [first, other])) is None


def test_finishing_a_job_sends_a_shows_query_only_when_it_has_one(requests):
    ingest_jobs.finish_job(_ARTIST, "added", show_id=1, shows_query="bandId=7&fromDate=2027-01-21&toDate=2027-01-24")
    ingest_jobs.finish_job(_TICKETWEB, "added", show_id=2)
    assert requests[0][2]["json"]["new_shows_query"] == "bandId=7&fromDate=2027-01-21&toDate=2027-01-24"
    assert "new_shows_query" not in requests[1][2]["json"]   # works before migration 0008 for every job with one Show


def test_a_page_whose_shows_all_fail_fails_the_job(db, supabase):
    first = event_show(_PAGE, _URL)
    with patch("app.ingest_jobs.fetch_events", return_value=[first, _elsewhere(first, "924 Gilman", "Berkeley", 22)]), \
         patch("app.scheduler.ingest_shows", side_effect=RuntimeError("database is locked")):
        assert _run(db, [_ARTIST], _TODAY) == []
    assert supabase[-1] == ("finish", "job-6", "failed", {"message": "RuntimeError: database is locked",
                                                          "extracted": None})


@patch("app.ingest_jobs.fetch_events")
def test_a_job_an_earlier_run_finished_is_skipped(fetch, db, supabase):
    assert _run(db, [Job("job-1", 11, "ticketweb", _URL, None, "added")], _TODAY) == []
    fetch.assert_not_called()
    assert supabase == []


@patch("app.ingest_jobs.fetch_events", return_value=[event_show(_PAGE, _URL)])
def test_losing_supabase_stops_the_run(fetch, db):
    """The jobs stay on the queue and are handed out again."""
    with patch("app.ingest_jobs.update_jobs", side_effect=SupabaseError("down")):
        with pytest.raises(SupabaseError):
            _run(db, [_TICKETWEB], _TODAY)


# ── Supabase requests ─────────────────────────────────────────────────────────

@pytest.fixture
def requests(monkeypatch):
    monkeypatch.setattr("app.ingest_jobs.settings.supabase_url", "https://x.supabase.co/")
    monkeypatch.setattr("app.ingest_jobs.settings.supabase_service_role_key", "sb_secret_x")
    sent = []

    def request(method, url, **kwargs):
        sent.append((method, url, kwargs))
        body = [{"id": "job-1", "provider": "ticketweb", "url": _URL, "screenshot_path": None, "extracted": None,
                 "approved_at": None}]
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


@patch("app.ingest_jobs.fetch_events", return_value=[event_show(_PAGE, _URL)])
def test_a_job_that_added_a_show_is_finished_only_once_it_is_pushed(fetch, db, supabase):
    with patch("app.scheduler.ingest_shows", side_effect=_stored(db)):
        saved = run_jobs(db, [_TICKETWEB], _TODAY)

    # Still running and on the queue: if the commit or push fails, the run's failure step fails it and the queue
    # hands it out again.
    assert not [c for c in supabase if c[0] == "finish"]
    assert saved == [Saved("job-1", 11, saved[0].message, db.query(Show).one().id)]


# ── the commands ──────────────────────────────────────────────────────────────

@pytest.fixture
def keys_work():
    with patch("app.ingestion.lastfm.lastfm_key_problem", return_value=None), \
         patch("app.ingestion.discogs.discogs_key_problem", return_value=None):
        yield


@patch("app.cli.SessionLocal")
@patch("app.ingest_jobs.run_jobs", return_value=[Saved("job-1", 11, "Added it", 7)])
@patch("app.ingest_jobs.fetch_jobs", return_value=[_TICKETWEB, _SCREENSHOT])
def test_ingest_jobs_tells_the_workflow_which_jobs_added_a_show(fetch, run, session, db, keys_work, tmp_path,
                                                                 monkeypatch, capsys):
    session.return_value = db
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_RUN_ID", "99")
    monkeypatch.setenv("GITHUB_REPOSITORY", "jsturgis/the_list")

    main(["ingest-jobs", "--jobs", "job-1:11,job-2:12", "--outcomes", str(tmp_path / "added.json")])

    fetch.assert_called_once_with([("job-1", 11), ("job-2", 12)])
    assert run.call_args.args[3] == "https://github.com/jsturgis/the_list/actions/runs/99"
    assert output.read_text() == "added=job-1\n"
    assert "1 of 2 added" in capsys.readouterr().out


@patch("app.cli.SessionLocal")
@patch("app.ingest_jobs.finish_job")
@patch("app.ingest_jobs.run_jobs", return_value=[Saved("job-1", 11, "Added it", 7, None, "bandId=3")])
@patch("app.ingest_jobs.fetch_jobs", return_value=[_TICKETWEB])
def test_ingest_jobs_leaves_the_added_jobs_for_ingest_jobs_finish(fetch, run, finish, session, db, keys_work,
                                                                 tmp_path):
    session.return_value = db
    outcomes = tmp_path / "added.json"

    main(["ingest-jobs", "--jobs", "job-1:11", "--outcomes", str(outcomes)])
    finish.assert_not_called()

    main(["ingest-jobs-finish", "--outcomes", str(outcomes)])
    (job, status), fields = finish.call_args
    assert (job.id, job.msg_id, status) == ("job-1", 11, "added")
    assert fields == {"message": "Added it", "show_id": 7, "extracted": None, "shows_query": "bandId=3"}


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
        ("bands", "Checking the spelling of Teenage Bottlerocket"),   # no service has it (app/ingestion/spelling.py)
        ("bands", "Looking up Band 2 of 2: Brendan Kelly"),
        ("bands", "Checking the spelling of Brendan Kelly"),
        ("saving", None),
        ("embedding", None),
    ]


async def test_a_phase_that_cant_be_reported_doesnt_fail_the_ingest(db, services):
    def broken(phase, detail):
        raise SupabaseError("down")

    (show,) = await ingest_shows(db, [event_show(_PAGE, _URL)], on_phase=broken)
    assert show.source == "ticketweb"


def test_a_known_venues_city_is_looked_up_by_its_coordinates_else_its_name(db):
    from app.models.venue import Region, Venue

    db.add_all([Venue(name="Sandbar", city="Capitola", region=Region.sf, latitude=36.9720, longitude=-121.9530),
                Venue(name="Nowhere Hall", city="Unknown", region=Region.sf)])
    db.flush()
    venue_city = ingest_jobs.known_venue_city(db)
    assert venue_city("Some Bar", (36.9725, -121.9531)) == "Capitola"   # whatever its name, the Venue there
    assert venue_city("Sandbar", (39.74, -104.95)) is None             # given coordinates, its name doesn't count
    assert venue_city("Sandbar") == "Capitola"
    assert venue_city("Nowhere Hall") is None                           # a Venue with no city places nothing
