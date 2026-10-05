"""Command-line entry point.

    python -m app.cli ingest                              # maintenance, then import the newest edition
    python -m app.cli export --out ../frontend/export
    python -m app.cli alerts                              # send this week's Alert emails
    python -m app.cli alerts --dry-run                    # print them instead
    python -m app.cli alerts --only me@example.com        # send only to one person (a test)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.alerts import SendError, SupabaseError, run_alerts
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ingest", help="run daily maintenance, then ingest the newest edition")
    export_cmd = commands.add_parser("export", help="write the static JSON data files")
    export_cmd.add_argument("--out", required=True, help="directory to write shows/venues/bands/meta.json into")
    alerts_cmd = commands.add_parser("alerts", help="build this week's Alert emails from everyone's Saved Filters")
    alerts_cmd.add_argument("--dry-run", action="store_true", help="print the emails instead of sending them")
    alerts_cmd.add_argument("--only", metavar="EMAIL", help="build and send only this person's Alert (a test send)")
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


if __name__ == "__main__":
    main()
