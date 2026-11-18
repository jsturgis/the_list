"""Tests for the maintainer's emails about the ingest (app/notifications.py): one after each successful ingest, and
one a day once it has been failing for two weeks."""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest

from app import notifications
from app.clock import local_today
from app.mailer import SendError
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.notifications import (
    FAILING_AFTER_DAYS, LOG_TAIL_CHARS, LOG_TAIL_LINES, LastSuccess, actions_run_url, failure_due, failure_email,
    notify_failure, notify_success, redact, root_cause, success_email, tail,
)

NOW = datetime(2026, 11, 28, 9, 30)
SITE = "https://list.example"

_TRACEBACK = '''Traceback (most recent call last):
  File "/src/app/scheduler.py", line 112, in _run_ingestion_async
    the_list = fetch_list()
               ^^^^^^^^^^^^
  File "/src/app/ingestion/steve_list.py", line 60, in fetch_list
    raise ListError(f"couldn't fetch {url}: {exc}") from exc
app.ingestion.steve_list.ListError: couldn't fetch https://stevelist.com/list: timed out
'''

_CHAINED = '''Traceback (most recent call last):
  File "/src/app/pipeline/embed.py", line 20, in embed
    response = httpx.post(url)
httpx.ConnectError: [Errno 111] Connection refused

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/src/app/cli.py", line 60, in ingest
    asyncio.run(_run_ingestion_async())
  File "/src/app/pipeline/embed.py", line 22, in embed
    raise RuntimeError("Ollama is down") from exc
RuntimeError: Ollama is down
'''


def _run(db, finished, status=IngestionStatus.success, **kwargs):
    run = IngestionRun(started_at=finished - timedelta(minutes=5), finished_at=finished, status=status, **kwargs)
    db.add(run)
    db.commit()
    return run


class FakeResend:
    """Resend's send-email endpoint: records each email; like Resend, answers 409 to a different email sent with an
    Idempotency-Key it has seen, and drops a repeat of the same one."""

    def __init__(self):
        self.sent: list[tuple[dict, dict]] = []  # (json body, headers)
        self.keys: dict[str, dict] = {}
        self.status = 200

    def post(self, url, json=None, headers=None, **kwargs):
        assert url == "https://api.resend.com/emails"
        assert headers["Authorization"] == "Bearer re_test"
        status = self.status
        key = headers.get("Idempotency-Key")
        if status == 200 and key in self.keys:
            if self.keys[key] != json:
                status = 409
        elif status == 200:
            self.sent.append((json, headers))
            if key:
                self.keys[key] = json
        return httpx.Response(status, json={"id": "email-1"}, request=httpx.Request("POST", url))


@pytest.fixture
def resend():
    fake = FakeResend()
    with patch("app.notifications.settings") as s, patch("app.mailer.httpx.post", side_effect=fake.post):
        s.maintainer_email, s.resend_api_key, s.alerts_from = "maintainer@example.com", "re_test", "The List <alerts@list.example>"
        s.site_url = SITE
        s.google_maps_api_key = s.lastfm_api_key = s.discogs_consumer_key = s.discogs_consumer_secret = None
        s.supabase_service_role_key = s.anthropic_api_key = ""
        yield fake


@pytest.fixture
def no_actions_run(monkeypatch):
    for name in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
        monkeypatch.delenv(name, raising=False)


# ── the root cause ────────────────────────────────────────────────────────────

def test_the_root_cause_is_the_exception_a_traceback_ends_with():
    assert root_cause(_TRACEBACK) == \
        "app.ingestion.steve_list.ListError: couldn't fetch https://stevelist.com/list: timed out"


def test_the_root_cause_of_a_chained_exception_is_the_final_one_with_what_caused_it():
    assert root_cause(_CHAINED) == \
        "RuntimeError: Ollama is down (caused by httpx.ConnectError: [Errno 111] Connection refused)"


def test_the_root_cause_is_found_in_a_log_with_lines_after_the_traceback():
    log = ("2026-11-28 09:00:01,100 INFO app.scheduler: ingestion: fetching the List\n"
           "2026-11-28 09:00:02,200 ERROR app.cli: ingest failed\n" + _CHAINED +
           "2026-11-28 09:00:02,300 INFO app.database: closing\n")
    assert root_cause(log).startswith("RuntimeError: Ollama is down")


def test_the_root_cause_of_a_traceback_cut_short_is_its_last_line():
    # A run keeps the last 2000 characters of its traceback, which can lose the header.
    assert root_cause(_TRACEBACK[60:].replace("Traceback (most recent call last):", "")) == \
        "app.ingestion.steve_list.ListError: couldn't fetch https://stevelist.com/list: timed out"


def test_the_root_cause_of_a_failed_check_is_its_error_line():
    log = ("INFO  [alembic.runtime.migration] Context impl SQLiteImpl.\n"
           "2026-11-28 09:00:01,100 ERROR app.cli: check failed: ListError: couldn't fetch https://stevelist.com/list: 503\n")
    assert root_cause(log) == "ListError: couldn't fetch https://stevelist.com/list: 503"


def test_the_root_cause_falls_back_to_the_last_line_and_is_none_without_text():
    assert root_cause("pulling models\ncurl: (22) The requested URL returned error: 500\n") == \
        "curl: (22) The requested URL returned error: 500"
    assert root_cause("") is None and root_cause(None) is None and root_cause(" \n") is None


def test_the_root_cause_is_one_line_of_limited_length():
    cause = root_cause("Traceback (most recent call last):\n  File \"x.py\", line 1\nValueError: " + "x" * 2000)
    assert "\n" not in cause and len(cause) <= 500


# ── the log tail and redaction ────────────────────────────────────────────────

def test_the_tail_is_the_last_lines_of_the_log():
    log = "\n".join(f"line {i}" for i in range(1, 201)) + "\n"
    kept = tail(log).splitlines()
    assert len(kept) == LOG_TAIL_LINES and kept[0] == "line 141" and kept[-1] == "line 200"
    assert tail("one\ntwo\n") == "one\ntwo"
    assert tail("") == ""


def test_the_tail_is_capped_in_characters_keeping_the_end():
    kept = tail("\n".join("x" * 500 + f" {i}" for i in range(60)))
    assert len(kept) == LOG_TAIL_CHARS and kept.startswith("…") and kept.endswith(" 59")


@pytest.mark.parametrize("secret_text, kept", [
    ("GET https://ws.audioscrobbler.com/2.0/?method=artist.gettoptags&api_key=abc123def456&format=json", "&format=json"),
    ("https://maps.googleapis.com/maps/api/place/findplacefromtext/json?input=Chapel&key=abc123def456", "input=Chapel"),
    ("https://api.example.com/x?token=abc123def456&page=2", "&page=2"),
    ("https://api.example.com/x?access_token=abc123def456", "https://api.example.com/x?"),
    ("https://api.discogs.com/artists/1?key=ck&secret=abc123def456", "artists/1"),
    ("Authorization: Bearer abc123def456", "Authorization: Bearer"),
    ("headers={'Authorization': 'Bearer abc123def456'}", "headers="),
    ("Authorization: Discogs key=abc123def456, secret=abc123def456x", "Authorization:"),
    ("authorization=abc123def456", "authorization="),
])
def test_credentials_are_redacted(secret_text, kept):
    redacted = redact(secret_text)
    assert "abc123def456" not in redacted and "[redacted]" in redacted
    assert kept in redacted


def test_known_secrets_are_redacted_wherever_they_appear_and_the_rest_is_left():
    assert redact("the key re_live_9f8e7d6c was refused", ("re_live_9f8e7d6c",)) == "the key [redacted] was refused"
    plain = "ListError: couldn't fetch https://stevelist.com/list: timed out"
    assert redact(plain) == plain


# ── when the failure email is due ─────────────────────────────────────────────

def test_a_failure_email_is_due_once_the_last_success_is_two_weeks_old():
    assert FAILING_AFTER_DAYS == 14
    assert failure_due(NOW - timedelta(days=14), NOW)
    assert failure_due(NOW - timedelta(days=30), NOW)
    assert not failure_due(NOW - timedelta(days=14) + timedelta(minutes=1), NOW)
    assert not failure_due(NOW - timedelta(hours=1), NOW)


def test_no_failure_email_is_due_without_a_successful_ingest():
    assert not failure_due(None, NOW)


def test_the_actions_run_link_needs_all_three_variables():
    env = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "someone/the_list", "GITHUB_RUN_ID": "42"}
    assert actions_run_url(env) == "https://github.com/someone/the_list/actions/runs/42"
    assert actions_run_url({**env, "GITHUB_RUN_ID": ""}) is None
    assert actions_run_url({}) is None


# ── the emails ────────────────────────────────────────────────────────────────

def test_the_success_email_gives_the_edition_the_show_counts_and_the_new_bands_and_venues():
    run = IngestionRun(started_at=NOW, finished_at=NOW, status=IngestionStatus.success,
                       edition_title="The List for Nov 27, 2026", edition_date=date(2026, 11, 27), shows_parsed=1205,
                       shows_upserted=1200, shows_new=40, new_bands=12, new_bands_without_photo_pct=25.0, new_venues=2)
    email = success_email(run, SITE)

    assert email.subject == "The List: ingest succeeded: 12 new bands, 2 new venues"
    for version in (email.text, email.html):
        assert "The List for Nov 27, 2026 (2026-11-27)" in version
        assert "1205 parsed, 1200 upserted, 40 new" in version
        assert "12 (25% without a photo)" in version
        assert SITE in version
    assert "New Venues: 2" in email.text
    assert "New Bands: 12 (25% without a photo)" in email.text


def test_the_success_email_counts_nothing_new_as_zero():
    run = IngestionRun(started_at=NOW, status=IngestionStatus.success, new_bands=1, new_venues=None)
    email = success_email(run, SITE)
    assert email.subject == "The List: ingest succeeded: 1 new band, 0 new venues"
    assert "New Bands: 1\n" in email.text and "New Venues: 0\n" in email.text


def test_the_failure_email_gives_the_cause_the_stage_the_last_success_the_log_and_the_run():
    last = LastSuccess(NOW - timedelta(days=15, hours=2), "The List for Nov 13, 2026", date(2026, 11, 13))
    email = failure_email(stage="check", cause="ListError: couldn't fetch https://stevelist.com/list: 503",
                          log_tail="line 1\n<line 2>", last=last, now=NOW,
                          run_url="https://github.com/someone/the_list/actions/runs/42")

    assert email.subject == \
        "The List: ingest failing for 15 days: ListError: couldn't fetch https://stevelist.com/list: 503"
    assert "Root cause: ListError: couldn't fetch https://stevelist.com/list: 503" in email.text
    assert "Failed stage: check" in email.text
    assert "Last successful ingest: 2026-11-13 07:30 UTC, 15 days ago (The List for Nov 13, 2026)" in email.text
    assert "line 1\n<line 2>" in email.text
    assert "https://github.com/someone/the_list/actions/runs/42" in email.text
    assert "at most once a day" in email.text
    assert "line 1\n&lt;line 2&gt;" in email.html and "couldn&#x27;t fetch" in email.html
    assert 'href="https://github.com/someone/the_list/actions/runs/42"' in email.html


def test_the_failure_email_has_no_run_link_outside_actions_and_a_short_subject():
    last = LastSuccess(NOW - timedelta(days=20), None, None)
    email = failure_email(stage="ingest", cause="ValueError: " + "x" * 400, log_tail="", last=last, now=NOW,
                          run_url=None)
    assert "GitHub Actions" not in email.text and "href" not in email.html
    assert len(email.subject) < 170 and email.subject.endswith("…")
    assert "The end of the log" not in email.text


# ── notify-success ────────────────────────────────────────────────────────────

def test_notify_success_emails_the_maintainer_about_the_newest_run(db, resend):
    _run(db, NOW - timedelta(days=7), new_bands=99)
    _run(db, NOW, edition_title="The List for Nov 27, 2026", shows_parsed=3, shows_upserted=3, shows_new=1,
         new_bands=12, new_venues=2)

    notify_success(db, dry_run=False, out=io.StringIO())

    (body, headers), = resend.sent
    assert body["to"] == ["maintainer@example.com"] and body["from"] == "The List <alerts@list.example>"
    assert body["subject"] == "The List: ingest succeeded: 12 new bands, 2 new venues"
    assert "New Venues: 2" in body["text"] and "<table" in body["html"]
    assert "maintainer@example.com" not in headers["Idempotency-Key"]
    # A re-run of the step sends the same email with the same key, which Resend drops.
    notify_success(db, dry_run=False, out=io.StringIO())
    assert len(resend.sent) == 1


def test_notify_success_sends_nothing_when_the_newest_run_failed_or_there_is_none(db, resend):
    assert notify_success(db, dry_run=False, out=io.StringIO()) is None
    _run(db, NOW - timedelta(days=7))
    _run(db, NOW, status=IngestionStatus.failure, error=_TRACEBACK)
    assert notify_success(db, dry_run=False, out=io.StringIO()) is None
    assert resend.sent == []


@pytest.mark.parametrize("shows_new", [0, None])
def test_notify_success_sends_nothing_when_the_ingest_brought_no_new_shows(db, resend, caplog, shows_new):
    _run(db, NOW, shows_parsed=1200, shows_upserted=1200, shows_new=shows_new, new_bands=0, new_venues=0)
    with caplog.at_level("INFO"):
        assert notify_success(db, dry_run=False, out=io.StringIO()) is None
        assert notify_success(db, dry_run=True, out=io.StringIO()) is None
    assert resend.sent == []
    assert "no new Shows" in caplog.text


def test_an_ingest_with_warnings_is_emailed_even_without_new_shows(db, resend):
    _run(db, NOW, shows_parsed=1200, shows_upserted=1200, shows_new=0, new_bands=0, new_venues=0,
         warnings=[{"message": "venue calendars skipped this run", "count": 1},
                   {"message": "MusicBrainz didn't answer: ConnectError", "count": 3}])

    email = notify_success(db, dry_run=False, out=io.StringIO())

    assert email.subject == "The List: ingest succeeded: 0 new bands, 0 new venues, 2 warnings"
    assert "It carried on past 2 warnings" in email.text
    assert "Warning: MusicBrainz didn't answer: ConnectError (3 times)" in email.text
    assert len(resend.sent) == 1


def test_a_dry_run_prints_the_success_email_instead_of_sending_it(db, resend):
    _run(db, NOW, shows_new=1, new_bands=3, new_venues=1)
    out = io.StringIO()
    notify_success(db, dry_run=True, out=out)
    assert resend.sent == []
    assert out.getvalue().startswith(
        "To: maintainer@example.com\nSubject: The List: ingest succeeded: 3 new bands, 1 new venue\n\n")


@pytest.mark.parametrize("missing", ["maintainer_email", "resend_api_key"])
def test_without_a_recipient_or_a_resend_key_nothing_is_sent_and_nothing_fails(db, resend, caplog, missing):
    setattr(notifications.settings, missing, "")
    _run(db, NOW - timedelta(days=20))
    with caplog.at_level("INFO"):
        assert notify_success(db, dry_run=False, out=io.StringIO()) is None
        assert notify_failure(db, stage="check", log_path=None, dry_run=False, out=io.StringIO(), now=NOW) is None
    assert resend.sent == []
    assert "skipping" in caplog.text


def test_a_failed_send_raises_without_quoting_resend(db, resend):
    _run(db, NOW, shows_new=1)
    resend.status = 422
    with pytest.raises(SendError, match="HTTP 422"):
        notify_success(db, dry_run=False, out=io.StringIO())


# ── notify-failure ────────────────────────────────────────────────────────────

def test_notify_failure_emails_once_the_last_success_is_two_weeks_old(db, resend, tmp_path, no_actions_run):
    _run(db, NOW - timedelta(days=15), edition_title="The List for Nov 13, 2026", edition_date=date(2026, 11, 13))
    log = tmp_path / "check.log"
    log.write_text("2026-11-28 09:30:00,000 ERROR app.cli: check failed: ListError: couldn't fetch "
                   "https://stevelist.com/list?api_key=abc123def456: 503\n")

    notify_failure(db, stage="check", log_path=str(log), dry_run=False, out=io.StringIO(), now=NOW)

    (body, headers), = resend.sent
    assert body["to"] == ["maintainer@example.com"]
    assert body["subject"] == ("The List: ingest failing for 15 days: ListError: couldn't fetch "
                               "https://stevelist.com/list?api_key=[redacted]: 503")
    assert "Failed stage: check" in body["text"]
    assert "15 days ago (The List for Nov 13, 2026)" in body["text"]
    assert "app.cli: check failed" in body["text"]                       # the end of the log
    assert "abc123def456" not in body["text"] + body["html"] + body["subject"]
    assert "GitHub Actions" not in body["text"]
    assert headers["Idempotency-Key"].startswith(f"ingest-failure-{local_today().isoformat()}-")
    assert "maintainer@example.com" not in headers["Idempotency-Key"]


def test_notify_failure_links_the_actions_run(db, resend, monkeypatch):
    _run(db, NOW - timedelta(days=15))
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/the_list")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    notify_failure(db, stage="check", log_path=None, dry_run=False, out=io.StringIO(), now=NOW)
    assert "https://github.com/someone/the_list/actions/runs/42" in resend.sent[0][0]["text"]


def test_notify_failure_sends_nothing_before_two_weeks_or_without_a_successful_ingest(db, resend, caplog):
    with caplog.at_level("INFO"):
        assert notify_failure(db, stage="check", log_path=None, dry_run=False, out=io.StringIO(), now=NOW) is None
    assert "no successful ingest yet" in caplog.text
    _run(db, NOW - timedelta(days=30), status=IngestionStatus.failure, error=_TRACEBACK)   # not a success
    assert notify_failure(db, stage="ingest", log_path=None, dry_run=False, out=io.StringIO(), now=NOW) is None
    _run(db, NOW - timedelta(days=13))
    assert notify_failure(db, stage="ingest", log_path=None, dry_run=False, out=io.StringIO(), now=NOW) is None
    assert resend.sent == []


def test_a_failed_ingests_root_cause_comes_from_its_run_and_the_log_tail_from_the_log(db, resend, tmp_path):
    _run(db, NOW - timedelta(days=21))
    _run(db, NOW, status=IngestionStatus.failure, error=_CHAINED)
    log = tmp_path / "ingest.log"
    log.write_text("\n".join(f"line {i}" for i in range(1, 101)) + "\n")

    notify_failure(db, stage="ingest", log_path=str(log), dry_run=False, out=io.StringIO(), now=NOW)

    body = resend.sent[0][0]
    assert body["subject"].startswith("The List: ingest failing for 21 days: RuntimeError: Ollama is down")
    assert "Failed stage: ingest" in body["text"]
    assert "line 41\n" in body["text"] and "line 100\n" in body["text"] and "line 40\n" not in body["text"]


def test_a_failed_ingest_without_a_failed_run_takes_its_root_cause_from_the_log(db, resend, tmp_path):
    # Maintenance or a migration failed before the ingestion run was recorded.
    _run(db, NOW - timedelta(days=21))
    log = tmp_path / "ingest.log"
    log.write_text("2026-11-28 09:30:00,000 ERROR app.cli: ingest failed\n" + _TRACEBACK)
    notify_failure(db, stage="ingest", log_path=str(log), dry_run=False, out=io.StringIO(), now=NOW)
    assert "ListError: couldn't fetch https://stevelist.com/list: timed out" in resend.sent[0][0]["subject"]


def test_a_failure_without_a_log_still_emails(db, resend, tmp_path):
    _run(db, NOW - timedelta(days=21))
    notify_failure(db, stage="ingest", log_path=str(tmp_path / "missing.log"), dry_run=False, out=io.StringIO(),
                   now=NOW)
    assert "unknown: the ingest job failed without a log" in resend.sent[0][0]["text"]


def test_the_settings_keys_are_redacted_from_the_email(db, resend, tmp_path):
    notifications.settings.lastfm_api_key = "0123456789abcdef"
    _run(db, NOW - timedelta(days=21))
    _run(db, NOW, status=IngestionStatus.failure,
         error="Traceback (most recent call last):\n  File \"x.py\", line 1\nRuntimeError: bad 0123456789abcdef\n")
    log = tmp_path / "ingest.log"
    log.write_text("GET /2.0/ 0123456789abcdef\nAuthorization: Bearer re_live_secret\n")

    notify_failure(db, stage="ingest", log_path=str(log), dry_run=False, out=io.StringIO(), now=NOW)

    body = resend.sent[0][0]
    everything = body["subject"] + body["text"] + body["html"]
    assert "0123456789abcdef" not in everything and "re_live_secret" not in everything
    assert "RuntimeError: bad [redacted]" in body["subject"]


def test_at_most_one_failure_email_a_day(db, resend, tmp_path, caplog):
    _run(db, NOW - timedelta(days=21))
    log = tmp_path / "check.log"
    log.write_text("2026-11-28 09:30:00,000 ERROR app.cli: check failed: ListError: 503\n")
    assert notify_failure(db, stage="check", log_path=str(log), dry_run=False, out=io.StringIO(), now=NOW)

    # The next hour's failure is a different email with the day's key: Resend refuses it, and that isn't an error.
    log.write_text("2026-11-28 10:30:00,000 ERROR app.cli: check failed: ListError: 503\n")
    with caplog.at_level("INFO"):
        assert notify_failure(db, stage="check", log_path=str(log), dry_run=False, out=io.StringIO(),
                              now=NOW + timedelta(hours=1)) is None
    assert len(resend.sent) == 1
    assert "today's email went out already" in caplog.text

    # The next day has a new key.
    with patch("app.notifications.local_today", return_value=local_today() + timedelta(days=1)):
        assert notify_failure(db, stage="check", log_path=str(log), dry_run=False, out=io.StringIO(),
                              now=NOW + timedelta(days=1))
    assert len(resend.sent) == 2


def test_a_dry_run_prints_the_failure_email_due_or_not(db, resend, tmp_path):
    _run(db, NOW - timedelta(days=3))
    log = tmp_path / "check.log"
    log.write_text("2026-11-28 09:30:00,000 ERROR app.cli: check failed: ListError: 503\n")
    out = io.StringIO()
    notify_failure(db, stage="check", log_path=str(log), dry_run=True, out=out, now=NOW)
    assert resend.sent == []
    assert "Subject: The List: ingest failing for 3 days: ListError: 503\n" in out.getvalue()


# ── the commands ──────────────────────────────────────────────────────────────

def test_cli_notify_success_sends_and_exits_non_zero_only_when_the_send_fails(db, resend, capsys):
    from app.cli import main

    _run(db, datetime.utcnow(), shows_new=1, new_bands=3, new_venues=1)
    with patch("app.cli.SessionLocal", return_value=db):
        main(["notify-success", "--dry-run"])
        assert "Subject: The List: ingest succeeded" in capsys.readouterr().out
        main(["notify-success"])
        assert len(resend.sent) == 1

        notifications.settings.maintainer_email = ""
        main(["notify-success"])            # not configured: skipped, exit status 0
        assert len(resend.sent) == 1

        notifications.settings.maintainer_email = "maintainer@example.com"
        resend.status = 500
        with pytest.raises(SystemExit) as exit_:
            main(["notify-success"])
        assert exit_.value.code == 1


def test_cli_notify_failure_reads_the_stage_and_the_log(db, resend, tmp_path, capsys):
    from app.cli import main

    _run(db, datetime.utcnow() - timedelta(days=16))
    log = tmp_path / "check.log"
    log.write_text("2026-11-28 09:30:00,000 ERROR app.cli: check failed: ListError: 503\n")
    with patch("app.cli.SessionLocal", return_value=db):
        main(["notify-failure", "--stage", "check", "--log", str(log), "--dry-run"])
        assert "Subject: The List: ingest failing for 16 days: ListError: 503" in capsys.readouterr().out
        assert resend.sent == []
        main(["notify-failure", "--stage", "check", "--log", str(log)])
        assert "Failed stage: check" in resend.sent[0][0]["text"]

        with pytest.raises(SystemExit):
            main(["notify-failure", "--stage", "deploy"])     # only the check and the ingest
