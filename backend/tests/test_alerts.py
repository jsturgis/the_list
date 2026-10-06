"""Tests for the weekly Alerts run: Saved Filters from Supabase, matched against the Shows in the database."""
from __future__ import annotations

import io
import json
import logging
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.alerts import SendError, SupabaseError, run_alerts
from app.clock import local_today
from app.models.act import Act
from app.models.band import Band
from app.models.show import AgeRestriction, Show, ShowStatus
from app.models.venue import Region, Venue

SITE = "https://list.example"
SUPABASE = "https://ref.supabase.co"


# ── seeded database ───────────────────────────────────────────────────────────

def _venue(db, name, city="Berkeley", region=Region.east_bay):
    v = Venue(name=name, city=city, region=region)
    db.add(v)
    db.flush()
    return v


def _show(db, venue, days, headliner, *support, genres=("punk",), status=ShowStatus.upcoming, **kw):
    s = Show(date=local_today() + timedelta(days=days), venue_id=venue.id, status=status, **kw)
    db.add(s)
    db.flush()
    for position, name in enumerate((headliner, *support)):
        band = db.query(Band).filter_by(name=name).first() or Band(name=name, genres=list(genres))
        db.add(band)
        db.flush()
        db.add(Act(show_id=s.id, band_id=band.id, position=position))
    db.flush()
    return s


@pytest.fixture
def shows(db):
    gilman = _venue(db, "924 Gilman Street")
    chapel = _venue(db, "The Chapel", city="San Francisco", region=Region.sf)
    return {
        "counterparts": _show(db, gilman, 1, "Counterparts", "Drought"),
        "sundale": _show(db, gilman, 3, "Sundale", age_restriction=AgeRestriction.plus_21),
        "jazz": _show(db, chapel, 2, "Snarky Puppy", genres=("jazz",), is_free=True),
        "past": _show(db, gilman, -2, "Old News"),
        "cancelled": _show(db, gilman, 4, "Called Off", status=ShowStatus.cancelled),
    }


# ── fake Supabase ─────────────────────────────────────────────────────────────

def _response(body, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.side_effect = lambda: body
    r.raise_for_status.side_effect = None if status < 400 else RuntimeError(f"HTTP {status}")
    return r


class FakeSupabase:
    """Serves the three Supabase endpoints the Alerts run reads, and records what was asked for."""

    def __init__(self):
        self.users: list[dict] = []
        self.subscriptions: list[dict] = []
        self.saved_filters: list[dict] = []
        self.requests: list[tuple[str, dict, dict]] = []
        self.fail = False

    def person(self, email, *filters, enabled=True):
        user_id = f"user-{len(self.users) + 1}"
        self.users.append({"id": user_id, "email": email})
        self.subscriptions.append({"user_id": user_id, "enabled": enabled, "unsubscribe_token": f"token-{user_id}"})
        for name, query in filters:
            self.saved_filters.append({"user_id": user_id, "name": name, "query": query,
                                       "created_at": f"2026-10-01T00:00:{len(self.saved_filters):02d}Z"})

    def get(self, url, params=None, headers=None, **kwargs):
        params, headers = params or {}, headers or {}
        self.requests.append((url, params, headers))
        if self.fail:
            return _response({"message": "boom"}, status=500)
        assert headers.get("apikey") == "sb_secret_test"
        if url == f"{SUPABASE}/auth/v1/admin/users":
            page, per_page = int(params["page"]), int(params["per_page"])
            return _response({"users": self.users[(page - 1) * per_page:page * per_page]})
        # PostgREST pages with limit/offset.
        window = slice(int(params.get("offset", 0)), int(params.get("offset", 0)) + int(params.get("limit", 10**9)))
        if url == f"{SUPABASE}/rest/v1/alert_subscriptions":
            rows = [r for r in self.subscriptions if params.get("enabled") != "eq.true" or r["enabled"]]
            return _response(rows[window])
        if url == f"{SUPABASE}/rest/v1/saved_filters":
            return _response(sorted(self.saved_filters, key=lambda r: r["created_at"])[window])
        raise AssertionError(f"unexpected request {url}")


class FakeResend:
    """Resend's send-email endpoint: records each email, and fails for the recipients in `fail_for`."""

    def __init__(self):
        self.sent: list[tuple[dict, dict]] = []  # (json body, headers)
        self.fail_for: set[str] = set()

    def post(self, url, json=None, headers=None, **kwargs):
        assert url == "https://api.resend.com/emails"
        assert headers["Authorization"] == "Bearer re_test"
        if json["to"][0] in self.fail_for:
            return _response({"message": "rejected"}, status=422)
        self.sent.append((json, headers))
        return _response({"id": f"email-{len(self.sent)}"})


@pytest.fixture
def resend():
    return FakeResend()


@pytest.fixture
def supabase(resend):
    fake = FakeSupabase()
    with patch("app.alerts.settings") as s, patch("app.alerts.httpx.get", side_effect=fake.get), \
            patch("app.alerts.httpx.post", side_effect=resend.post), patch("app.alerts.time.sleep"):
        s.supabase_url, s.supabase_service_role_key, s.site_url = SUPABASE, "sb_secret_test", SITE
        s.resend_api_key, s.alerts_from = "re_test", "The List <alerts@list.example>"
        yield fake


def _run(db):
    out = io.StringIO()
    emails = run_alerts(db, dry_run=True, out=out)
    return emails, out.getvalue()


# ── the run ───────────────────────────────────────────────────────────────────

def test_one_email_per_person_grouped_by_saved_filter(db, shows, supabase):
    supabase.person("fan@example.com", ("East Bay punk", "genre=punk&region=east_bay"), ("Free", "free=1"))
    emails, printed = _run(db)

    [email] = emails
    assert email.to == "fan@example.com"
    assert email.subject == "3 upcoming shows matched your saved search"
    assert [section.name for section in email.sections] == ["East Bay punk", "Free"]
    punk, free = email.sections
    assert [s.headliner for s in punk.shows] == ["Counterparts", "Sundale"]  # date order; past and cancelled left out
    assert [s.headliner for s in free.shows] == ["Snarky Puppy"]
    assert "To: fan@example.com" in printed and "East Bay punk" in printed
    # The plain-text version follows the HTML's layout: header, intro, a heading per Saved Filter, footer.
    assert email.text.startswith("THE LIST · SF Bay Area Music\n\n3 upcoming shows matched your saved search.\n")
    heading = "East Bay punk · 2 shows"
    assert f"\n{heading}\n{'=' * len(heading)}\n" in email.text
    assert email.text.endswith(f"You set up these alerts on The List.\nManage your alerts: {SITE}/alerts/\n"
                               f"Unsubscribe from these emails: {SITE}/alerts/unsubscribe/?token=token-user-1\n")


def test_each_show_gives_date_headliner_venue_city_and_link(db, shows, supabase):
    supabase.person("fan@example.com", ("Free", "free=1"))
    [email], _ = _run(db)

    jazz = shows["jazz"]
    day = jazz.date
    assert f"{day:%a, %b} {day.day} · Snarky Puppy\n  The Chapel · San Francisco\n  Free\n  {SITE}/shows/{jazz.id}/\n" in email.text
    assert f'href="{SITE}/shows/{jazz.id}/"' in email.html
    assert f"{SITE}/alerts/" in email.text and f'href="{SITE}/alerts/"' in email.html  # manage your alerts
    assert email.html.startswith("<!doctype html>") and "</html>" in email.html  # a whole document, ready to send


def test_each_show_gives_support_acts_doors_price_age_and_marks(db, supabase):
    from datetime import time

    venue = _venue(db, "The Independent", city="San Francisco", region=Region.sf)
    show = _show(db, venue, 5, "Headliner", "Two", "Three", "Four", "Five", "Six", door_time=time(19, 30),
                 price_min=15, price_max=20, age_restriction=AgeRestriction.plus_21,
                 is_recommended=True, is_sold_out=True, will_sell_out=True)
    supabase.person("fan@example.com", ("SF", "region=sf"))
    [email], _ = _run(db)

    day = show.date
    assert (f"{day:%a, %b} {day.day} · Headliner\n"
            f"  with Two, Three, Four + 2 more\n"
            f"  The Independent · San Francisco\n"
            f"  Doors 7:30 PM · $15–$20 · 21+\n"
            f"  Steve's Pick · Sold out · Will sell out\n"
            f"  {SITE}/shows/{show.id}/\n") in email.text
    for part in ("Headliner</a>", "with Two, Three, Four + 2 more", "Doors 7:30 PM · $15–$20 · 21+",
                 "Steve&#x27;s Pick", "Sold out", "Will sell out", f">{day:%a}<", f">{day:%b} {day.day}<"):
        assert part in email.html, part


def test_matches_agree_with_the_graphql_show_query(db, client, shows, supabase):
    supabase.person("fan@example.com", ("21+", "age=21%2B"), ("Search", "q=sundal"), ("Genre", "genre=jazz"))
    [email], _ = _run(db)

    for section, gql_filter in zip(email.sections, ['ageRestriction: "21+"', 'search: "sundal"', 'genre: "jazz"']):
        resp = client.post("/graphql", json={"query": f"{{ shows(filters: {{ {gql_filter} }}) {{ id }} }}"})
        expected = [int(s["id"]) for s in resp.json()["data"]["shows"]]
        assert [s.show_id for s in section.shows] == expected, section.name


def test_old_band_and_venue_links_still_match(db, shows, supabase):
    supabase.person("fan@example.com", ("Old link", "band=counterparts&venue=gilman"))
    [email], _ = _run(db)
    assert [s.headliner for s in email.sections[0].shows] == ["Counterparts"]


def test_band_and_venue_alerts_match_by_id(db, shows, supabase):
    drought = db.query(Band).filter_by(name="Drought").one()  # a support Act, not a headliner
    chapel = shows["jazz"].venue_id
    supabase.person("fan@example.com", ("Drought", f"bandId={drought.id}"), ("The Chapel", f"venueId={chapel}"),
                    ("Not an id", "bandId=abc&genre=jazz"))
    [email], _ = _run(db)
    assert [[s.headliner for s in section.shows] for section in email.sections] == [
        ["Counterparts"], ["Snarky Puppy"], ["Snarky Puppy"],
    ]


def test_at_most_25_shows_per_saved_filter_then_a_see_all_link(db, supabase):
    venue = _venue(db, "The Fillmore", city="San Francisco", region=Region.sf)
    for day in range(30):
        _show(db, venue, day, f"Band {day:02d}")
    supabase.person("fan@example.com", ("SF", "region=sf"))
    [email], _ = _run(db)

    [section] = email.sections
    assert len(section.shows) == 25 and section.total == 30
    assert f"See all 30 on The List: {SITE}/?region=sf" in email.text
    # The headline counts every match, not only the 25 listed.
    assert email.subject == "30 upcoming shows matched your saved search"
    assert "30 upcoming shows matched your saved search.<" in email.html


def test_the_headline_counts_each_matching_show_once_across_alerts(db, shows, supabase):
    supabase.person("fan@example.com", ("East Bay punk", "genre=punk&region=east_bay"), ("Punk", "genre=punk"),
                    ("Counterparts", "q=counterparts"))
    [email], _ = _run(db)
    assert [s.total for s in email.sections] == [2, 2, 1]
    assert email.subject == "2 upcoming shows matched your saved search"


def test_saved_filters_and_people_with_no_matches_are_left_out(db, shows, supabase):
    supabase.person("fan@example.com", ("Nothing", "genre=polka"), ("Free", "free=1"))
    supabase.person("other@example.com", ("Nothing either", "genre=polka"))
    emails, printed = _run(db)

    assert [e.to for e in emails] == ["fan@example.com"]
    assert [s.name for s in emails[0].sections] == ["Free"]
    assert "other@example.com" not in printed


def test_alerts_with_the_same_filters_are_merged_under_the_first_name(db, shows, supabase):
    supabase.person("fan@example.com", ("East Bay punk", "genre=punk&region=east_bay"), ("Free", "free=1"),
                    ("punk · East Bay", "region=east_bay&genre=PUNK"))
    [email], _ = _run(db)
    assert [s.name for s in email.sections] == ["East Bay punk", "Free"]
    assert email.text.count("Counterparts") == 1


def test_people_who_turned_alerts_off_are_skipped(db, shows, supabase):
    supabase.person("off@example.com", ("Free", "free=1"), enabled=False)
    supabase.person("on@example.com", ("Free", "free=1"))
    emails, _ = _run(db)

    assert [e.to for e in emails] == ["on@example.com"]
    [(_, params, _)] = [r for r in supabase.requests if r[0].endswith("/alert_subscriptions")]
    assert params["enabled"] == "eq.true"


def test_reads_every_page_of_people(db, shows, supabase):
    for n in range(1, 1003):
        supabase.person(f"fan{n}@example.com", ("Free", "free=1"))
    emails, _ = _run(db)
    assert len(emails) == 1002


def test_logs_counts_but_no_email_addresses(db, shows, supabase, caplog):
    supabase.person("fan@example.com", ("Free", "free=1"))
    with caplog.at_level(logging.INFO):
        _run(db)
    assert "1 alert email" in caplog.text
    assert "fan@example.com" not in caplog.text


def test_a_supabase_error_fails_the_run(db, shows, supabase):
    supabase.fail = True
    with pytest.raises(SupabaseError):
        _run(db)


def test_missing_supabase_settings_fail_clearly(db):
    with patch("app.alerts.settings") as s:
        s.supabase_url, s.supabase_service_role_key = "", ""
        with pytest.raises(SupabaseError, match="SUPABASE_URL"):
            run_alerts(db, dry_run=True, out=io.StringIO())


# ── sending ───────────────────────────────────────────────────────────────────

def test_sends_each_alert_through_resend_with_both_versions_and_an_unsubscribe_link(db, shows, supabase, resend):
    supabase.person("fan@example.com", ("Free", "free=1"))
    supabase.person("other@example.com", ("East Bay punk", "genre=punk&region=east_bay"))
    emails = run_alerts(db, dry_run=False, out=io.StringIO())

    assert [body["to"] for body, _ in resend.sent] == [["fan@example.com"], ["other@example.com"]]
    body, headers = resend.sent[0]
    email = emails[0]
    unsubscribe = f"{SITE}/alerts/unsubscribe/?token=token-user-1"
    assert body["from"] == "The List <alerts@list.example>"
    assert (body["subject"], body["html"], body["text"]) == (email.subject, email.html, email.text)
    assert body["headers"] == {"List-Unsubscribe": f"<{unsubscribe}>"}
    assert unsubscribe in email.text and f'href="{unsubscribe}"' in email.html
    # The same person, the same day, the same email: Resend drops a repeat, so re-running doesn't email
    # anyone twice. The content is part of the key, so a key is never reused for a different email (Resend
    # would refuse it).
    key = headers["Idempotency-Key"]
    assert key.startswith(f"alert-{local_today().isoformat()}-token-user-1-")
    resend.sent.clear()
    run_alerts(db, dry_run=False, out=io.StringIO())
    assert resend.sent[0][1]["Idempotency-Key"] == key
    _show(db, _venue(db, "The Fillmore", city="San Francisco"), 6, "New Show", is_free=True)
    resend.sent.clear()
    run_alerts(db, dry_run=False, out=io.StringIO())
    assert resend.sent[0][1]["Idempotency-Key"] != key


def test_a_dry_run_sends_nothing(db, shows, supabase, resend):
    supabase.person("fan@example.com", ("Free", "free=1"))
    _run(db)
    assert resend.sent == []


def test_a_failed_send_doesnt_stop_the_others_but_fails_the_run(db, shows, supabase, resend, caplog):
    supabase.person("bounce@example.com", ("Free", "free=1"))
    supabase.person("fan@example.com", ("Free", "free=1"))
    resend.fail_for = {"bounce@example.com"}

    with caplog.at_level(logging.INFO), pytest.raises(SendError, match="1 of 2"):
        run_alerts(db, dry_run=False, out=io.StringIO())
    assert [body["to"] for body, _ in resend.sent] == [["fan@example.com"]]
    assert "example.com" not in caplog.text


def test_only_sends_to_the_one_recipient_asked_for(db, shows, supabase, resend):
    supabase.person("fan@example.com", ("Free", "free=1"))
    supabase.person("me@example.com", ("Free", "free=1"))
    run_alerts(db, dry_run=False, out=io.StringIO(), only="ME@example.com")
    assert [body["to"] for body, _ in resend.sent] == [["me@example.com"]]
    # A test send can be repeated the same day (the weekly run's idempotency key would make Resend refuse it).
    assert "Idempotency-Key" not in resend.sent[0][1]


def test_sending_without_a_resend_key_fails_before_sending_anything(db, shows, supabase, resend):
    supabase.person("fan@example.com", ("Free", "free=1"))
    with patch("app.alerts.settings.resend_api_key", ""), pytest.raises(SendError, match="RESEND_API_KEY"):
        run_alerts(db, dry_run=False, out=io.StringIO())
    assert resend.sent == []


def test_cli_dry_run_prints_and_exits_non_zero_on_supabase_errors(db, shows, supabase, capsys):
    from app.cli import main

    supabase.person("fan@example.com", ("Free", "free=1"))
    with patch("app.cli.SessionLocal", return_value=db):
        main(["alerts", "--dry-run"])
    assert "To: fan@example.com" in capsys.readouterr().out

    supabase.fail = True
    with patch("app.cli.SessionLocal", return_value=db), pytest.raises(SystemExit) as exit:
        main(["alerts", "--dry-run"])
    assert exit.value.code == 1


def test_cli_sends_and_can_send_to_one_recipient(db, shows, supabase, resend):
    from app.cli import main

    supabase.person("fan@example.com", ("Free", "free=1"))
    supabase.person("me@example.com", ("Free", "free=1"))
    db.commit()  # the CLI closes its session, which would roll back uncommitted test data
    with patch("app.cli.SessionLocal", return_value=db):
        main(["alerts", "--only", "me@example.com"])
    assert [body["to"] for body, _ in resend.sent] == [["me@example.com"]]

    resend.fail_for = {"fan@example.com"}
    with patch("app.cli.SessionLocal", return_value=db), pytest.raises(SystemExit) as exit:
        main(["alerts"])
    assert exit.value.code == 1
