"""Command-line entry point.

    python -m app.cli export --out ../frontend/public/data
"""
from __future__ import annotations

import argparse
import logging

from app.database import SessionLocal
from app.export import export


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    export_cmd = commands.add_parser("export", help="write the static JSON data files")
    export_cmd.add_argument("--out", required=True, help="directory to write shows/venues/bands/meta.json into")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.command == "export":
        db = SessionLocal()
        try:
            counts = export(db, args.out)
        finally:
            db.close()
        print(f"exported to {args.out}: " + ", ".join(f"{n} {name}" for name, n in counts.items()))


if __name__ == "__main__":
    main()
