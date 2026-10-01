from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from url_kb.export.source_packet import export_source_packet
from url_kb.ingest.service import ingest_batch
from url_kb.search.service import search_sources, update_review_status
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

    if args.command == "search_sources":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        result = search_sources(
            repository,
            query=args.query,
            domain=args.domain,
            review_status=args.review_status,
        )
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return

    if args.command == "update_review_status":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        result = update_review_status(
            repository,
            record_id=args.record_id,
            review_status=args.review_status,
        )
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return

    if args.command == "export_source_packet":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        result = export_source_packet(
            repository,
            query=args.query,
            domain=args.domain,
            review_status=args.review_status,
            output_path=args.output,
        )
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

    search_parser = subparsers.add_parser("search_sources", help="Search persisted URL records")
    search_parser.add_argument("--query", help="Keyword query over URL/domain/source fields")
    search_parser.add_argument("--domain", help="Exact domain filter")
    search_parser.add_argument(
        "--review-status",
        choices=["pending_review", "reviewed", "rejected"],
        help="Review status filter",
    )
    search_parser.add_argument(
        "--database-url",
        default=os.environ.get("URL_KB_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="SQLite database URL, for example sqlite:///./data/url_kb.sqlite3",
    )

    update_parser = subparsers.add_parser(
        "update_review_status",
        help="Update a persisted URL record review status",
    )
    update_parser.add_argument("record_id", type=int, help="Persisted url_records.id value")
    update_parser.add_argument(
        "review_status",
        choices=["pending_review", "reviewed", "rejected"],
        help="New review status",
    )
    update_parser.add_argument(
        "--database-url",
        default=os.environ.get("URL_KB_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="SQLite database URL, for example sqlite:///./data/url_kb.sqlite3",
    )

    export_parser = subparsers.add_parser(
        "export_source_packet",
        help="Export searched URL records to a draft Markdown source packet",
    )
    export_parser.add_argument("--query", help="Keyword query over URL/domain/source fields")
    export_parser.add_argument("--domain", help="Exact domain filter")
    export_parser.add_argument(
        "--review-status",
        choices=["pending_review", "reviewed", "rejected"],
        help="Review status filter",
    )
    export_parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Markdown output path. Defaults to "
            "outputs/source_packets/<timestamp>_source_packet.md"
        ),
    )
    export_parser.add_argument(
        "--database-url",
        default=os.environ.get("URL_KB_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="SQLite database URL, for example sqlite:///./data/url_kb.sqlite3",
    )

    return parser


if __name__ == "__main__":
    main()
