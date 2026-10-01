from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from url_kb.enrich.providers import DEFAULT_PROMPT_VERSION, SUPPORTED_PROVIDERS
from url_kb.enrich.service import (
    DEFAULT_ENRICH_LIMIT,
    ENRICHMENT_REVIEW_DECISIONS,
    EnrichmentNotFoundError,
    enrich_sources,
    list_enrichments,
    review_enrichment,
    show_enrichment,
)
from url_kb.export.source_packet import export_source_packet
from url_kb.ingest.service import (
    PRIVATE_CORPUS_PROFILES,
    ingest_batch,
    ingest_private_corpus_csvs,
)
from url_kb.metrics.service import (
    DEFAULT_LATEST_RUNS_LIMIT,
    DEFAULT_MULTI_OCCURRENCE_LIMIT,
    DEFAULT_TOP_DOMAINS_LIMIT,
    corpus_metrics,
)
from url_kb.search.service import search_sources, update_review_status
from url_kb.storage.sqlite_repo import ENRICHMENT_REVIEW_STATUSES, SQLiteURLRepository

DEFAULT_DATABASE_URL = "sqlite:///./data/url_kb.sqlite3"
DEFAULT_PRIVATE_CORPUS_PATH = Path("private/url_corpus")
DEFAULT_PRIVATE_DATABASE_URL = "sqlite:///./data/private_url_kb.sqlite3"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest_batch":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        result = ingest_batch(args.csv_path, repository)
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return

    if args.command == "ingest_private_corpus":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        try:
            result = ingest_private_corpus_csvs(
                args.corpus_path,
                repository,
                profiles=args.profile,
            )
        except (FileNotFoundError, ValueError) as error:
            parser.error(str(error))
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

    if args.command == "enrich_sources":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        result = enrich_sources(
            repository,
            query=args.query,
            domain=args.domain,
            review_status=args.review_status,
            limit=args.limit,
            provider_name=args.provider,
            model=args.model,
            prompt_version=args.prompt_version,
            dry_run=args.dry_run,
        )
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return

    if args.command == "list_enrichments":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        result = list_enrichments(
            repository,
            status=args.status,
            provider=args.provider,
            limit=args.limit,
        )
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return

    if args.command == "show_enrichment":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        try:
            result = show_enrichment(repository, enrichment_id=args.enrichment_id)
        except EnrichmentNotFoundError as error:
            parser.error(str(error))
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return

    if args.command == "review_enrichment":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        try:
            result = review_enrichment(
                repository,
                enrichment_id=args.enrichment_id,
                status=args.status,
                reviewer_note=args.note,
            )
        except (EnrichmentNotFoundError, ValueError) as error:
            parser.error(str(error))
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return

    if args.command == "corpus_metrics":
        repository = SQLiteURLRepository.from_database_url(args.database_url)
        try:
            result = corpus_metrics(
                repository,
                latest_runs_limit=args.latest_runs_limit,
                top_domains_limit=args.top_domains_limit,
                multi_occurrence_limit=args.multi_occurrence_limit,
            )
        except ValueError as error:
            parser.error(str(error))
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

    private_corpus_parser = subparsers.add_parser(
        "ingest_private_corpus",
        help="Ingest supported private URL corpus sources into a local ignored DB",
    )
    private_corpus_parser.add_argument(
        "--corpus-path",
        type=Path,
        default=Path(os.environ.get("URL_KB_PRIVATE_CORPUS_PATH", DEFAULT_PRIVATE_CORPUS_PATH)),
        help="Private URL corpus directory. Defaults to private/url_corpus.",
    )
    private_corpus_parser.add_argument(
        "--profile",
        action="append",
        choices=sorted(PRIVATE_CORPUS_PROFILES),
        help=(
            "Private corpus profile to ingest. May be repeated. Defaults to all "
            "supported profiles."
        ),
    )
    private_corpus_parser.add_argument(
        "--database-url",
        default=os.environ.get("URL_KB_PRIVATE_DATABASE_URL", DEFAULT_PRIVATE_DATABASE_URL),
        help=(
            "SQLite database URL for private corpus data. Defaults to "
            "sqlite:///./data/private_url_kb.sqlite3"
        ),
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

    enrich_parser = subparsers.add_parser(
        "enrich_sources",
        help="Create draft AI enrichment rows for searched URL records",
    )
    enrich_parser.add_argument("--query", help="Keyword query over URL/domain/source fields")
    enrich_parser.add_argument("--domain", help="Exact domain filter")
    enrich_parser.add_argument(
        "--review-status",
        choices=["pending_review", "reviewed", "rejected"],
        help="Review status filter",
    )
    enrich_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_ENRICH_LIMIT,
        help=f"Maximum records to enrich. Defaults to {DEFAULT_ENRICH_LIMIT}",
    )
    enrich_parser.add_argument(
        "--provider",
        choices=sorted(SUPPORTED_PROVIDERS),
        default="mock",
        help="Enrichment provider. MVP supports deterministic mock only",
    )
    enrich_parser.add_argument(
        "--model",
        help="Provider model identifier. Defaults to the provider's safe local value",
    )
    enrich_parser.add_argument(
        "--prompt-version",
        default=DEFAULT_PROMPT_VERSION,
        help=f"Prompt contract version. Defaults to {DEFAULT_PROMPT_VERSION}",
    )
    enrich_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show selected records without writing enrichment rows",
    )
    enrich_parser.add_argument(
        "--database-url",
        default=os.environ.get("URL_KB_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="SQLite database URL, for example sqlite:///./data/url_kb.sqlite3",
    )

    list_enrichments_parser = subparsers.add_parser(
        "list_enrichments",
        help="List AI enrichment drafts and review states",
    )
    list_enrichments_parser.add_argument(
        "--status",
        choices=sorted(ENRICHMENT_REVIEW_STATUSES),
        help="Enrichment review status filter",
    )
    list_enrichments_parser.add_argument("--provider", help="Provider filter")
    list_enrichments_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum enrichment rows to list",
    )
    list_enrichments_parser.add_argument(
        "--database-url",
        default=os.environ.get("URL_KB_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="SQLite database URL, for example sqlite:///./data/url_kb.sqlite3",
    )

    show_enrichment_parser = subparsers.add_parser(
        "show_enrichment",
        help="Show one AI enrichment draft with URL metadata",
    )
    show_enrichment_parser.add_argument(
        "enrichment_id",
        type=int,
        help="Persisted ai_enrichments.id value",
    )
    show_enrichment_parser.add_argument(
        "--database-url",
        default=os.environ.get("URL_KB_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="SQLite database URL, for example sqlite:///./data/url_kb.sqlite3",
    )

    review_enrichment_parser = subparsers.add_parser(
        "review_enrichment",
        help="Approve or reject an AI enrichment draft",
    )
    review_enrichment_parser.add_argument(
        "enrichment_id",
        type=int,
        help="Persisted ai_enrichments.id value",
    )
    review_enrichment_parser.add_argument(
        "status",
        choices=sorted(ENRICHMENT_REVIEW_DECISIONS),
        help="Human review decision",
    )
    review_enrichment_parser.add_argument("--note", help="Reviewer note")
    review_enrichment_parser.add_argument(
        "--database-url",
        default=os.environ.get("URL_KB_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="SQLite database URL, for example sqlite:///./data/url_kb.sqlite3",
    )

    metrics_parser = subparsers.add_parser(
        "corpus_metrics",
        help="Report aggregate corpus health metrics without raw URL lists",
    )
    metrics_parser.add_argument(
        "--latest-runs-limit",
        type=int,
        default=DEFAULT_LATEST_RUNS_LIMIT,
        help=f"Maximum latest ingest runs to include. Defaults to {DEFAULT_LATEST_RUNS_LIMIT}",
    )
    metrics_parser.add_argument(
        "--top-domains-limit",
        type=int,
        default=DEFAULT_TOP_DOMAINS_LIMIT,
        help=f"Maximum top domains to include. Defaults to {DEFAULT_TOP_DOMAINS_LIMIT}",
    )
    metrics_parser.add_argument(
        "--multi-occurrence-limit",
        type=int,
        default=DEFAULT_MULTI_OCCURRENCE_LIMIT,
        help=(
            "Maximum multi-occurrence record examples to include. Defaults to "
            f"{DEFAULT_MULTI_OCCURRENCE_LIMIT}"
        ),
    )
    metrics_parser.add_argument(
        "--database-url",
        default=os.environ.get("URL_KB_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="SQLite database URL, for example sqlite:///./data/url_kb.sqlite3",
    )

    return parser


if __name__ == "__main__":
    main()
