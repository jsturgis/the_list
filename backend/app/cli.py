"""Command-line entry point.

    python -m app.cli check                               # has Steve's List changed since the last ingest?
    python -m app.cli ingest                              # maintenance, then ingest the List as it is now
    python -m app.cli add-event https://www.ticketweb.com/event/...   # add a Show from an event page (any site)
    python -m app.cli ingest-jobs --jobs JOB_ID:MSG_ID,...   # run the Admin page's ingest jobs (the Ingest jobs workflow)
    python -m app.cli ingest-jobs-phase --jobs JOB_ID,... --phase committing   # ... and record how far they've got
    python -m app.cli ingest-jobs-finish --outcomes PATH   # ... and finish those that added Shows, once pushed
    python -m app.cli export --out ../frontend/export
    python -m app.cli alerts                              # send this week's Alert emails
    python -m app.cli alerts --dry-run                    # print them instead
    python -m app.cli alerts --only me@example.com        # send only to one person (a test)
    python -m app.cli notify-success                      # email the maintainer about the ingest that just succeeded
    python -m app.cli notify-failure --stage ingest --log ingest.log   # ... or, after two weeks of failures, why
    python -m app.cli backfill --max-minutes 300          # look existing Bands up on the services (resumable)
    python -m app.cli backfill --redo "Sunblind"          # ... first redoing a Band matched to the wrong artist
    python -m app.cli backfill --recheck-photos           # ... first marking Bands that could have a Bandcamp photo
    python -m app.cli backfill --recheck-calendars        # ... first marking every checked Venue to look again
    python -m app.cli photo-focus                         # focal points for stored Band photos without one
    python -m app.cli photo-focus --all                   # ... or for every stored Band photo
    python -m app.cli venue-photos                        # store Venue photos that are still remote URLs
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from app import notifications
from app.alerts import SendError, SupabaseError, run_alerts
from app.config import settings
from app.database import SessionLocal
from app.export import export
from app.ingest_jobs import PHASES, STATUSES
from app.ingestion.steve_list import ListError, fetch_list
from app.scheduler import _run_ingestion_async, alerts_due, list_status, mark_alerts_sent, run_daily_maintenance

logger = logging.getLogger(__name__)


def check() -> None:
    """Fetch the List and say whether it has changed since the last successful ingest, whether it's a new edition,
    and whether the newest edition ingested is still due its Alerts (an earlier run couldn't send them):
    `changed=`, `new_edition=` and `alerts_due=true|false`, printed and, in a GitHub Actions job, written to the
    step's outputs. The Deploy workflow runs this hourly and ingests only a changed List. Exits 1 when the List
    can't be fetched.
    """
    db = SessionLocal()
    try:
        page = fetch_list()
        status = {**list_status(db, page), "alerts_due": alerts_due(db)}
    except ListError as exc:
        logger.error("check failed: %s: %s", type(exc).__name__, exc)
        sys.exit(1)
    finally:
        db.close()
    lines = [f"{name}={str(value).lower()}" for name, value in status.items()]
    print(f"the List for {page.edition_date}: " + ", ".join(lines))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as f:
            f.write("\n".join(lines) + "\n")


def ingest() -> None:
    """Mark Past Shows and delete old ones, then ingest the List as Steve's page has it now, changed or not.

    Exits 1 when either step fails (the failed ingestion run is recorded in the database).
    """
    try:
        run_daily_maintenance()
        asyncio.run(_run_ingestion_async())
    except Exception:
        logger.exception("ingest failed")
        sys.exit(1)


def add_event(url: str) -> None:
    """Add the Show on an event page (any site, app/ingestion/event_page.py) to the database, or each in the Bay Area on
    a page listing several, looking their new Venues and Bands up as the ingest does. Run it against the data branch's database (DATABASE_URL), and push that. An event
    Steve already lists only adds its ticket link: the List wins. Exits 1 when the page can't be read, isn't a Bay
    Area event, or a service key the lookups need is missing or rejected.
    """
    from app.ingest_jobs import add_show, describe
    from app.ingestion.event_page import EventError, fetch_events

    _require_service_keys("add-event")
    try:
        shows = fetch_events(url)
    except EventError as exc:
        sys.exit(f"add-event: {exc}")
    db = SessionLocal()
    try:
        for data in shows:
            show, listed = add_show(db, data)
            if listed:
                print(f"add-event: the List already has it (show {show.id}: {describe(show)}); added its ticket link")
            else:
                print(f"add-event: show {show.id}: {describe(show)}")
    finally:
        db.close()


def _require_service_keys(command: str) -> None:
    """Exit unless the Last.fm and Discogs keys work: the lookups treat a missing key as "nothing found" and mark
    the Bands looked up, so they'd never be asked again."""
    from app.ingestion.discogs import discogs_key_problem
    from app.ingestion.lastfm import lastfm_key_problem

    problems = [p for p in (lastfm_key_problem(), discogs_key_problem()) if p]
    if problems:
        sys.exit(f"{command}: " + "; ".join(problems))


def ingest_jobs(specs: str, outcomes: str | None = None) -> None:
    """Run the Admin page's ingest jobs (app/ingest_jobs.py), given as "job_id:msg_id,..." (the worker's), against
    the data branch's database, recording each job's progress and outcome in Supabase. A job that fails is recorded
    and doesn't stop the others. Writes `added=<job ids>` (the jobs that added a Show) to the step's outputs in a
    GitHub Actions job. Those jobs aren't finished yet: they're written to `outcomes`, for `ingest-jobs-finish` once
    the data is pushed; without `outcomes` (run by hand) they're finished now. Exits 1 when Supabase can't be
    reached or a service key is missing or rejected; the jobs then stay on the queue and are tried again.
    """
    from app.clock import local_today
    from app.ingest_jobs import fetch_jobs, finish_saved, parse_specs, run_jobs, save_outcomes

    _require_service_keys("ingest-jobs")
    try:
        jobs = fetch_jobs(parse_specs(specs))
    except (ValueError, SupabaseError) as exc:
        sys.exit(f"ingest-jobs: {exc}")
    run_url = None
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ['GITHUB_REPOSITORY']}"
                   f"/actions/runs/{os.environ['GITHUB_RUN_ID']}")
    db = SessionLocal()
    try:
        added = run_jobs(db, jobs, local_today(), run_url)
        if outcomes:
            save_outcomes(added, outcomes)
        else:
            finish_saved(added)
    except SupabaseError as exc:
        sys.exit(f"ingest-jobs: {exc}")
    finally:
        db.close()
    print(f"ingest-jobs: {len(added)} of {len(jobs)} added")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as f:
            f.write(f"added={','.join(s.job_id for s in added)}\n")


def ingest_jobs_finish(outcomes: str) -> None:
    """Finish the ingest jobs `ingest-jobs --outcomes` saved, once their Shows are pushed: each is "added" and off the
    queue. Exits 1 when Supabase can't be reached; the jobs then stay on the queue and are tried again."""
    from app.ingest_jobs import finish_saved, load_outcomes

    saved = load_outcomes(outcomes)
    try:
        finish_saved(saved)
    except SupabaseError as exc:
        sys.exit(f"ingest-jobs-finish: {exc}")
    print(f"ingest-jobs-finish: {len(saved)} job(s) added")


def ingest_jobs_phase(job_ids: str, phase: str | None, status: str | None, detail: str | None,
                      message: str | None, unfinished_only: bool) -> None:
    """Record how far these ingest jobs have got after ingesting (committing, deploying, live), or, with
    --unfinished-only, fail those a broken run left unfinished. Exits 1 when Supabase can't be reached."""
    from app.ingest_jobs import unfinished, update_jobs

    ids = [i.strip() for i in job_ids.split(",") if i.strip()]
    fields = {k: v for k, v in (("phase", phase), ("status", status), ("detail", detail), ("message", message))
              if v is not None}
    try:
        if unfinished_only:
            ids = unfinished(ids)
        update_jobs(ids, **fields)
    except SupabaseError as exc:
        sys.exit(f"ingest-jobs-phase: {exc}")
    print(f"ingest-jobs-phase: {len(ids)} job(s): " + ", ".join(f"{k}={v}" for k, v in fields.items()))


def alerts(dry_run: bool, only: str | None) -> None:
    """Build and send the weekly Alerts, then record on the newest edition's run that they went out (the Deploy
    workflow commits it), so the hourly check doesn't send them again; not for a dry run or a test send (--only).
    Exits 1 when Supabase can't be read or any send fails, recording nothing."""
    db = SessionLocal()
    try:
        run_alerts(db, dry_run=dry_run, out=sys.stdout, only=only)
        if not dry_run and not only and (run := mark_alerts_sent(db)):
            print(f"alerts: recorded as sent for {run.edition_title or run.edition_date}")
    except (SupabaseError, SendError) as exc:
        logger.error("alerts failed: %s", exc)
        sys.exit(1)
    finally:
        db.close()


def notify_success(dry_run: bool) -> None:
    """Email the maintainer about the ingest that just succeeded (app/notifications.py). Sends nothing, and exits 0,
    without MAINTAINER_EMAIL and RESEND_API_KEY; exits 1 only when the send itself fails."""
    _notify(lambda db: notifications.notify_success(db, dry_run=dry_run, out=sys.stdout))


def notify_failure(stage: str, log: str | None, dry_run: bool) -> None:
    """After a failed check or ingest, email the maintainer the root cause and the end of the log at `log`, when
    the ingest has been failing for two weeks and today's email hasn't gone out (app/notifications.py). Exits as
    notify-success does."""
    _notify(lambda db: notifications.notify_failure(db, stage=stage, log_path=log, dry_run=dry_run, out=sys.stdout))


def _notify(send) -> None:
    db = SessionLocal()
    try:
        send(db)
    except SendError as exc:
        logger.error("notify failed: %s", exc)
        sys.exit(1)
    finally:
        db.close()


def backfill(max_minutes: float, limit: int | None, recheck: bool = False, redo: list[str] | None = None,
             recheck_photos: bool = False, recheck_calendars: bool = False) -> None:
    """Look existing Bands up on the services until done, out of time or at the limit (see app/ingestion/backfill)."""
    from app.ingestion import backfill as backfills
    from app.ingestion.discogs import discogs_key_problem
    from app.ingestion.genre_filter import genre_model_problem
    from app.ingestion.lastfm import lastfm_key_problem

    # The lookups treat a missing or rejected key as "nothing found", and an unreachable genre model as "not a genre",
    # so the Bands would be marked looked up without them and never asked again: check all three work first.
    problems = [p for p in (lastfm_key_problem(), discogs_key_problem(), genre_model_problem()) if p]
    if problems:
        sys.exit("backfill: " + "; ".join(problems))

    db = SessionLocal()
    try:
        if recheck:
            print(f"backfill: {backfills.recheck_genres(db)} bands with tags that aren't genres, to look up again")
        if recheck_photos:
            print(f"backfill: {backfills.recheck_photos(db)} bands with a Bandcamp page and no service photo, "
                  "to look up again")
        if recheck_calendars:
            print(f"backfill: {backfills.recheck_calendars(db)} venues to look up their calendar again")
        if redo:
            if missing := backfills.redo_bands(db, redo, settings.images_path):
                sys.exit("backfill: no band named " + ", ".join(repr(name) for name in missing))
            print(f"backfill: {len(redo)} bands to look up again from scratch")
        result = asyncio.run(backfills.run_backfill(db, settings.images_path, max_minutes=max_minutes, limit=limit))
    finally:
        db.close()
    print(f"backfill: looked up {result['looked_up']} bands ({result['failed']} failed); "
          f"{result['remaining']} still to do")


def photo_focus(recompute: bool) -> None:
    """Work out the focal point of stored Band photos from the files in the images folder (no network)."""
    from app.ingestion.band_photos import fill_photo_focus

    db = SessionLocal()
    try:
        counts = fill_photo_focus(db, settings.images_path, recompute=recompute)
    finally:
        db.close()
    print(f"photo-focus: {counts['bands']} bands ({counts['with_faces']} photos with faces, {counts['faces']} faces); "
          f"{counts['skipped']} skipped (photo missing or unreadable)")


def venue_photos() -> None:
    """Store every Venue photo that's still a remote URL in the images folder, with its Commons credit."""
    from app.ingestion.venue_photos import store_venue_photos

    db = SessionLocal()
    try:
        counts = store_venue_photos(db, settings.images_path)
    finally:
        db.close()
    print(f"venue-photos: stored {counts['stored']} of {counts['pending']}; "
          f"{counts['remote']} still remote (try again later)")


def respell_bands(names: list[str] | None, apply: bool) -> None:
    """Put right the names of stored Bands listed misspelt (app/ingestion/respell_bands.py). Dry run without `apply`."""
    from app.embeddings.indexer import BAND_INDEX_PATH, remove_from_index
    from app.ingestion.band_sources import discogs_match
    from app.ingestion.discogs import discogs_artist, discogs_key_problem
    from app.ingestion.respell_bands import candidates, respell_stored
    from app.pipeline.enrichment import _enrich_band
    from app.scheduler import _respell

    # Without Discogs, a Band it has would look like one no service has: check it works first.
    if problem := discogs_key_problem():
        sys.exit(f"respell-bands: {problem}")

    def matched(name: str) -> bool:
        found = _enrich_band(name, False)
        return bool(found.get("mbid") or found.get("namesakes") or discogs_match(name, found, discogs_artist))

    db = SessionLocal()
    try:
        bands = candidates(db, names)
        if names and len(bands) < len(names):
            sys.exit("respell-bands: no band named " + ", ".join(
                repr(n) for n in names if n.casefold() not in {b.name.casefold() for b in bands}))
        print(f"respell-bands: checking {len(bands)} bands")
        done = respell_stored(db, bands, matched, _respell, apply=apply)
    finally:
        db.close()
    for respelt in done:
        print(f"respell-bands: {respelt}")
    merged = [r.band_id for r in done if r.merged_into]
    if apply and merged:
        remove_from_index(BAND_INDEX_PATH, merged)
    print(f"respell-bands: {'put right' if apply else 'would put right'} {len(done)} band names")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="say whether Steve's List has changed since the last ingest")
    commands.add_parser("ingest", help="run daily maintenance, then ingest Steve's List")
    add_cmd = commands.add_parser("add-event", help="add the Show on an event page (any site) to the database")
    add_cmd.add_argument("url", help="the event's page, e.g. https://www.ticketweb.com/event/...")
    jobs_cmd = commands.add_parser("ingest-jobs", help="run the Admin page's ingest jobs against the database")
    jobs_cmd.add_argument("--jobs", required=True, metavar="JOB_ID:MSG_ID,...", help="the jobs, as the worker gives them")
    jobs_cmd.add_argument("--outcomes", metavar="PATH",
                          help="write the jobs that added Shows here, to finish with ingest-jobs-finish once they're "
                               "pushed, rather than finishing them now")
    finish_cmd = commands.add_parser("ingest-jobs-finish",
                                     help="finish the ingest jobs that added Shows, once the data is pushed")
    finish_cmd.add_argument("--outcomes", required=True, metavar="PATH", help="what ingest-jobs --outcomes wrote")
    phase_cmd = commands.add_parser("ingest-jobs-phase", help="record how far ingest jobs have got after ingesting")
    phase_cmd.add_argument("--jobs", required=True, metavar="JOB_ID,...", help="the jobs")
    phase_cmd.add_argument("--phase", choices=PHASES)
    phase_cmd.add_argument("--status", choices=STATUSES)
    phase_cmd.add_argument("--detail")
    phase_cmd.add_argument("--message")
    phase_cmd.add_argument("--unfinished-only", action="store_true",
                           help="only the jobs still queued or running (a run that broke off)")
    export_cmd = commands.add_parser("export", help="write the static JSON data files")
    export_cmd.add_argument("--out", required=True, help="directory to write shows/venues/bands/meta.json into")
    alerts_cmd = commands.add_parser("alerts", help="build this week's Alert emails from everyone's Saved Filters")
    alerts_cmd.add_argument("--dry-run", action="store_true", help="print the emails instead of sending them")
    alerts_cmd.add_argument("--only", metavar="EMAIL", help="build and send only this person's Alert (a test send)")
    success_cmd = commands.add_parser("notify-success", help="email the maintainer about the ingest that just succeeded")
    success_cmd.add_argument("--dry-run", action="store_true", help="print the email instead of sending it")
    failure_cmd = commands.add_parser("notify-failure",
                                      help="email the maintainer when the ingest has been failing for two weeks")
    failure_cmd.add_argument("--stage", required=True, choices=notifications.STAGES, help="the job that just failed")
    failure_cmd.add_argument("--log", metavar="PATH", help="the failing command's output; its end goes in the email")
    failure_cmd.add_argument("--dry-run", action="store_true", help="print the email (due or not) instead of sending it")
    backfill_cmd = commands.add_parser("backfill", help="look existing Bands up on the services (resumable)")
    respell_cmd = commands.add_parser("respell-bands",
                                      help="put right stored Band names no service has, that a service has spelt right")
    respell_cmd.add_argument("--name", action="append", metavar="NAME",
                             help="a Band to check (repeatable); default: those on Upcoming Shows with no service data")
    respell_cmd.add_argument("--apply", action="store_true", help="make the changes (default: only say what they'd be)")
    backfill_cmd.add_argument("--max-minutes", type=float, default=300, help="stop after this long (default 300)")
    backfill_cmd.add_argument("--limit", type=int, default=None, help="look up at most this many Bands")
    backfill_cmd.add_argument("--recheck-genres", action="store_true",
                              help="first mark Bands whose genres hold a tag that isn't one, to look them up again")
    backfill_cmd.add_argument("--recheck-photos", action="store_true",
                              help="first mark Bands with a Bandcamp page and no service photo, to look them up again")
    backfill_cmd.add_argument("--recheck-calendars", action="store_true",
                              help="first mark every checked Venue to look for its calendar again")
    backfill_cmd.add_argument("--redo", action="append", metavar="NAME",
                              help="first drop what the services gave this Band (matched to the wrong artist) and look "
                                   "it up again from scratch; repeatable")
    focus_cmd = commands.add_parser("photo-focus", help="work out the focal point of stored Band photos (no network)")
    focus_cmd.add_argument("--all", action="store_true", help="every stored photo, not only those without a focal point")
    commands.add_parser("venue-photos", help="download Venue photos that are still remote URLs into the images folder")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
    if args.command == "check":
        check()
    elif args.command == "ingest":
        ingest()
    elif args.command == "add-event":
        add_event(args.url)
    elif args.command == "ingest-jobs":
        ingest_jobs(args.jobs, args.outcomes)
    elif args.command == "ingest-jobs-finish":
        ingest_jobs_finish(args.outcomes)
    elif args.command == "ingest-jobs-phase":
        ingest_jobs_phase(args.jobs, args.phase, args.status, args.detail, args.message, args.unfinished_only)
    elif args.command == "export":
        db = SessionLocal()
        try:
            counts = export(db, args.out)
        finally:
            db.close()
        print(f"exported to {args.out}: " + ", ".join(f"{n} {name}" for name, n in counts.items()))
    elif args.command == "alerts":
        alerts(dry_run=args.dry_run, only=args.only)
    elif args.command == "notify-success":
        notify_success(dry_run=args.dry_run)
    elif args.command == "notify-failure":
        notify_failure(stage=args.stage, log=args.log, dry_run=args.dry_run)
    elif args.command == "respell-bands":
        respell_bands(args.name, args.apply)
    elif args.command == "backfill":
        backfill(max_minutes=args.max_minutes, limit=args.limit, recheck=args.recheck_genres, redo=args.redo,
                 recheck_photos=args.recheck_photos, recheck_calendars=args.recheck_calendars)
    elif args.command == "photo-focus":
        photo_focus(recompute=args.all)
    elif args.command == "venue-photos":
        venue_photos()


if __name__ == "__main__":
    main()
