"""Command-line entry point.

    python -m app.cli ingest                              # maintenance, then import the newest edition
    python -m app.cli export --out ../frontend/export
    python -m app.cli alerts                              # send this week's Alert emails
    python -m app.cli alerts --dry-run                    # print them instead
    python -m app.cli alerts --only me@example.com        # send only to one person (a test)
    python -m app.cli backfill --max-minutes 300          # look existing Bands up on the services (resumable)
    python -m app.cli photo-focus                         # focal points for stored Band photos without one
    python -m app.cli photo-focus --all                   # ... or for every stored Band photo
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.alerts import SendError, SupabaseError, run_alerts
from app.config import settings
from app.database import SessionLocal
from app.export import export
from app.scheduler import _run_ingestion_async, run_daily_maintenance

logger = logging.getLogger(__name__)


def ingest() -> None:
    """Mark Past Shows and delete old ones, then ingest the newest edition from Drive.

    Exits 1 when either step fails (the failed ingestion run is recorded in the database); a week with
    no new edition is a success.
    """
    try:
        run_daily_maintenance()
        asyncio.run(_run_ingestion_async())
    except Exception:
        logger.exception("ingest failed")
        sys.exit(1)


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


def backfill(max_minutes: float, limit: int | None, recheck: bool = False) -> None:
    """Look existing Bands up on the services until done, out of time or at the limit (see app/ingestion/backfill)."""
    from app.ingestion.backfill import recheck_genres, run_backfill
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
            print(f"backfill: {recheck_genres(db)} bands with tags that aren't genres, to look up again")
        result = asyncio.run(run_backfill(db, settings.images_path, max_minutes=max_minutes, limit=limit))
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ingest", help="run daily maintenance, then ingest the newest edition")
    export_cmd = commands.add_parser("export", help="write the static JSON data files")
    export_cmd.add_argument("--out", required=True, help="directory to write shows/venues/bands/meta.json into")
    alerts_cmd = commands.add_parser("alerts", help="build this week's Alert emails from everyone's Saved Filters")
    alerts_cmd.add_argument("--dry-run", action="store_true", help="print the emails instead of sending them")
    alerts_cmd.add_argument("--only", metavar="EMAIL", help="build and send only this person's Alert (a test send)")
    backfill_cmd = commands.add_parser("backfill", help="look existing Bands up on the services (resumable)")
    backfill_cmd.add_argument("--max-minutes", type=float, default=300, help="stop after this long (default 300)")
    backfill_cmd.add_argument("--limit", type=int, default=None, help="look up at most this many Bands")
    backfill_cmd.add_argument("--recheck-genres", action="store_true",
                              help="first mark Bands whose genres hold a tag that isn't one, to look them up again")
    focus_cmd = commands.add_parser("photo-focus", help="work out the focal point of stored Band photos (no network)")
    focus_cmd.add_argument("--all", action="store_true", help="every stored photo, not only those without a focal point")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
    if args.command == "ingest":
        ingest()
    elif args.command == "export":
        db = SessionLocal()
        try:
            counts = export(db, args.out)
        finally:
            db.close()
        print(f"exported to {args.out}: " + ", ".join(f"{n} {name}" for name, n in counts.items()))
    elif args.command == "alerts":
        alerts(dry_run=args.dry_run, only=args.only)
    elif args.command == "backfill":
        backfill(max_minutes=args.max_minutes, limit=args.limit, recheck=args.recheck_genres)
    elif args.command == "photo-focus":
        photo_focus(recompute=args.all)


if __name__ == "__main__":
    main()
