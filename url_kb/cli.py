from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from url_kb.ingest.service import ingest_batch
from url_kb.storage.sqlite_repo import SQLiteURLRepository

DEFAULT_DATABASE_URL = "sqlite:///./data/url_kb.sqlite3"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest_batch":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        result = ingest_batch(args.csv_path, repository)
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return

    parser.print_help()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="url-kb")
    subparsers = parser.add_subparsers(dest="command")

    ingest_parser = subparsers.add_parser("ingest_batch", help="Ingest and persist a CSV URL batch")
    ingest_parser.add_argument(
        "csv_path",
        type=Path,
        nargs="?",
        default=Path("samples/public_urls.csv"),
        help="CSV file with a url column",
    )
    ingest_parser.add_argument(
        "--database-url",
        default=os.environ.get("URL_KB_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="SQLite database URL, for example sqlite:///./data/url_kb.sqlite3",
    )

    return parser


if __name__ == "__main__":
    main()
