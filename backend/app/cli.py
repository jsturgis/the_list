"""Command-line entry point.

    python -m app.cli check                               # has Steve's List changed since the last ingest?
    python -m app.cli ingest                              # maintenance, then ingest the List as it is now
    python -m app.cli add-event https://www.ticketweb.com/event/...   # add a Show from a TicketWeb event page
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
from app.ingestion.steve_list import ListError, fetch_list
from app.scheduler import _run_ingestion_async, list_status, run_daily_maintenance

logger = logging.getLogger(__name__)


def check() -> None:
    """Fetch the List and say whether it has changed since the last successful ingest, and whether it's a new
    edition: `changed=true|false` and `new_edition=true|false`, printed and, in a GitHub Actions job, written to the
    step's outputs. The Deploy workflow runs this hourly and ingests only a changed List. Exits 1 when the List
    can't be fetched.
    """
    db = SessionLocal()
    try:
        page = fetch_list()
        status = list_status(db, page)
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
    """Add the Show on an event page (TicketWeb, app/ingestion/ticketweb.py) to the database, looking its new Venue
    and Bands up as the ingest does. Run it against the data branch's database (DATABASE_URL), and push that. An event
    Steve already lists only adds its ticket link: the List wins. Exits 1 when the page can't be read, isn't a Bay
    Area event, or a service key the lookups need is missing or rejected.
    """
    from app.ingestion.discogs import discogs_key_problem
    from app.ingestion.lastfm import lastfm_key_problem
    from app.ingestion.ticketweb import EventError, fetch_event
    from app.scheduler import ingest_shows

    # The lookups treat a missing key as "nothing found" and mark the Bands looked up, so they'd never be asked again.
    problems = [p for p in (lastfm_key_problem(), discogs_key_problem()) if p]
    if problems:
        sys.exit("add-event: " + "; ".join(problems))
    try:
        data = fetch_event(url)
    except EventError as exc:
        sys.exit(f"add-event: {exc}")
    db = SessionLocal()
    try:
        (show,) = asyncio.run(ingest_shows(db, [data]))
        lineup = ", ".join(act.band.name for act in show.acts)
        where = f"{show.venue.name}, {show.venue.city}"
        if show.source == data["source"]:
            print(f"add-event: show {show.id}: {lineup} at {where} on {show.date:%a %b %-d, %Y}")
        else:
            print(f"add-event: the List already has it (show {show.id}: {lineup} at {where} on "
                  f"{show.date:%a %b %-d, %Y}); added its ticket link")
    finally:
        db.close()


def alerts(dry_run: bool, only: str | None) -> None:
    """Build and send the weekly Alerts; exits 1 when Supabase can't be read or any send fails."""
    db = SessionLocal()
    try:
        run_alerts(db, dry_run=dry_run, out=sys.stdout, only=only)
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="say whether Steve's List has changed since the last ingest")
    commands.add_parser("ingest", help="run daily maintenance, then ingest Steve's List")
    add_cmd = commands.add_parser("add-event", help="add the Show on an event page (TicketWeb) to the database")
    add_cmd.add_argument("url", help="the event's page, e.g. https://www.ticketweb.com/event/...")
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
    elif args.command == "backfill":
        backfill(max_minutes=args.max_minutes, limit=args.limit, recheck=args.recheck_genres, redo=args.redo,
                 recheck_photos=args.recheck_photos, recheck_calendars=args.recheck_calendars)
    elif args.command == "photo-focus":
        photo_focus(recompute=args.all)
    elif args.command == "venue-photos":
        venue_photos()


if __name__ == "__main__":
    main()
