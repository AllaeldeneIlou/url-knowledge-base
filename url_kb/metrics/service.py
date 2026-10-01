from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from url_kb.storage.sqlite_repo import SQLiteURLRepository

DEFAULT_LATEST_RUNS_LIMIT = 5
DEFAULT_TOP_DOMAINS_LIMIT = 10
DEFAULT_MULTI_OCCURRENCE_LIMIT = 10

SOURCE_FORMAT_DISPLAY_NAMES = {
    "csv_master_url_database": "csv_master",
    "csv_url_export": "csv_notion",
}


@dataclass(frozen=True)
class CorpusMetricsResult:
    url_record_count: int
    source_occurrence_count: int
    ingest_run_count: int
    dedupe_rate: float
    source_occurrences_by_format: dict[str, int]
    url_records_by_review_status: dict[str, int]
    ai_enrichments_by_status: dict[str, int]
    enrichment_coverage: dict[str, int | float]
    ingest_failures: dict[str, int | dict[str, int]]
    latest_ingest_runs: list[dict[str, object]]
    top_domains: list[dict[str, object]]
    records_with_multiple_occurrences: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def corpus_metrics(
    repository: SQLiteURLRepository,
    *,
    latest_runs_limit: int = DEFAULT_LATEST_RUNS_LIMIT,
    top_domains_limit: int = DEFAULT_TOP_DOMAINS_LIMIT,
    multi_occurrence_limit: int = DEFAULT_MULTI_OCCURRENCE_LIMIT,
) -> CorpusMetricsResult:
    _validate_positive_limit("latest_runs_limit", latest_runs_limit)
    _validate_positive_limit("top_domains_limit", top_domains_limit)
    _validate_positive_limit("multi_occurrence_limit", multi_occurrence_limit)

    repository.initialize()
    url_record_count = repository.count_url_records()
    source_occurrence_count = repository.count_source_occurrences()
    distinct_enriched_record_count = repository.count_distinct_enriched_url_records()
    failed_count, malformed_count, by_error_class = repository.ingest_failure_summary()
    multiple_occurrence_count = repository.count_records_with_multiple_occurrences()

    return CorpusMetricsResult(
        url_record_count=url_record_count,
        source_occurrence_count=source_occurrence_count,
        ingest_run_count=repository.count_ingest_runs(),
        dedupe_rate=_safe_ratio(
            source_occurrence_count - url_record_count,
            source_occurrence_count,
        ),
        source_occurrences_by_format=_safe_source_format_counts(
            repository.source_occurrences_by_format()
        ),
        url_records_by_review_status=repository.url_records_by_review_status(),
        ai_enrichments_by_status=repository.ai_enrichments_by_status(),
        enrichment_coverage={
            "enriched_record_count": distinct_enriched_record_count,
            "url_record_count": url_record_count,
            "coverage": _safe_ratio(distinct_enriched_record_count, url_record_count),
        },
        ingest_failures={
            "failed_count": failed_count,
            "malformed_count": malformed_count,
            "by_error_class": by_error_class,
        },
        latest_ingest_runs=[
            {
                "id": run.id,
                "source_file": Path(run.source_file).name,
                "input_count": run.input_count,
                "valid_count": run.valid_count,
                "inserted_count": run.inserted_count,
                "duplicate_count": run.duplicate_count,
                "malformed_count": run.malformed_count,
                "failed_count": run.failed_count,
                "status": run.status,
                "created_at": run.created_at,
            }
            for run in repository.latest_ingest_runs(latest_runs_limit)
        ],
        top_domains=[
            {"domain": domain, "count": count}
            for domain, count in repository.top_domains(top_domains_limit)
        ],
        records_with_multiple_occurrences={
            "count": multiple_occurrence_count,
            "top": [
                {
                    "url_record_id": record.url_record_id,
                    "domain": record.domain,
                    "occurrence_count": record.occurrence_count,
                }
                for record in repository.top_records_with_multiple_occurrences(
                    multi_occurrence_limit
                )
            ],
        },
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _safe_source_format_counts(source_counts: dict[str, int]) -> dict[str, int]:
    return {
        SOURCE_FORMAT_DISPLAY_NAMES.get(source_format, source_format): count
        for source_format, count in source_counts.items()
    }


def _validate_positive_limit(name: str, value: int) -> None:
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
