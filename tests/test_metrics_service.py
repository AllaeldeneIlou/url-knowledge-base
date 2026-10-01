from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from url_kb.ingest.normalize import normalize_url
from url_kb.metrics.service import corpus_metrics
from url_kb.storage.sqlite_repo import SQLiteURLRepository


def test_empty_database_metrics_are_valid_without_division_by_zero(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    result = corpus_metrics(repository)

    payload = result.to_dict()
    assert payload["url_record_count"] == 0
    assert payload["source_occurrence_count"] == 0
    assert payload["dedupe_rate"] == 0.0
    assert payload["enrichment_coverage"] == {
        "enriched_record_count": 0,
        "url_record_count": 0,
        "coverage": 0.0,
    }
    assert payload["source_occurrences_by_format"] == {}
    assert payload["top_domains"] == []


def test_corpus_metrics_counts_distributions_and_dedupe_rate(tmp_path: Path):
    repository = _seed_metrics_repository(tmp_path)

    result = corpus_metrics(repository, latest_runs_limit=2, top_domains_limit=3)

    payload = result.to_dict()
    assert payload["url_record_count"] == 3
    assert payload["source_occurrence_count"] == 5
    assert payload["ingest_run_count"] == 2
    assert payload["dedupe_rate"] == 0.4
    assert payload["source_occurrences_by_format"] == {
        "csv_master": 2,
        "markdown_links": 2,
        "csv_notion": 1,
    }
    assert payload["url_records_by_review_status"] == {
        "pending_review": 2,
        "reviewed": 1,
    }
    assert payload["ai_enrichments_by_status"] == {"approved": 1, "pending_review": 1}
    assert payload["ingest_failures"] == {
        "failed_count": 1,
        "malformed_count": 1,
        "by_error_class": {"malformed_url": 1},
    }


def test_enrichment_coverage_counts_distinct_enriched_records(tmp_path: Path):
    repository = _seed_metrics_repository(tmp_path)
    first_record = repository.list_url_records()[0]
    repository.insert_ai_enrichment(
        run_id="run-extra",
        url_record_id=first_record.id,
        provider="mock",
        model="mock-local-v1",
        prompt_version="url_metadata_v1",
        input_hash="hash-extra",
        status="pending_review",
        output_json="{}",
    )

    result = corpus_metrics(repository)

    assert result.to_dict()["enrichment_coverage"] == {
        "enriched_record_count": 2,
        "url_record_count": 3,
        "coverage": 0.6667,
    }


def test_top_domains_are_ordered_by_count_descending(tmp_path: Path):
    repository = _seed_metrics_repository(tmp_path)

    result = corpus_metrics(repository)

    assert result.to_dict()["top_domains"] == [
        {"domain": "example.com", "count": 2},
        {"domain": "docs.example.org", "count": 1},
    ]


def test_multi_occurrence_records_are_counted_without_urls(tmp_path: Path):
    repository = _seed_metrics_repository(tmp_path)

    result = corpus_metrics(repository)

    multi_occurrence = result.to_dict()["records_with_multiple_occurrences"]
    assert multi_occurrence["count"] == 2
    assert multi_occurrence["top"] == [
        {"url_record_id": 1, "domain": "example.com", "occurrence_count": 2},
        {"url_record_id": 2, "domain": "docs.example.org", "occurrence_count": 2},
    ]


def test_corpus_metrics_rejects_zero_or_negative_limits(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    with pytest.raises(ValueError, match="latest_runs_limit must be at least 1"):
        corpus_metrics(repository, latest_runs_limit=0)

    with pytest.raises(ValueError, match="top_domains_limit must be at least 1"):
        corpus_metrics(repository, top_domains_limit=0)

    with pytest.raises(ValueError, match="multi_occurrence_limit must be at least 1"):
        corpus_metrics(repository, multi_occurrence_limit=-1)


def test_corpus_metrics_cli_prints_valid_json(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    _seed_metrics_repository(tmp_path, database_path=database_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "url_kb.cli",
            "corpus_metrics",
            "--latest-runs-limit",
            "1",
            "--top-domains-limit",
            "1",
            "--multi-occurrence-limit",
            "1",
            "--database-url",
            f"sqlite:///{database_path}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["url_record_count"] == 3
    assert len(payload["latest_ingest_runs"]) == 1
    assert len(payload["top_domains"]) == 1
    assert len(payload["records_with_multiple_occurrences"]["top"]) == 1
    assert "canonical_url" not in completed.stdout
    assert "original_url" not in completed.stdout


def _seed_metrics_repository(
    tmp_path: Path, database_path: Path | None = None
) -> SQLiteURLRepository:
    repository = SQLiteURLRepository(database_path or tmp_path / "url_kb.sqlite3")
    repository.initialize()
    _inserted, first_id = repository.insert_url_record(
        normalize_url("https://example.com/a"),
        source_file="/private/corpus/master_url_database.csv",
    )
    repository.insert_source_occurrence(
        url_record_id=first_id,
        source_file="/private/corpus/master_url_database.csv",
        source_format="csv_master_url_database",
        original_url="https://example.com/a",
        row_number=2,
    )
    repository.insert_source_occurrence(
        url_record_id=first_id,
        source_file="/private/corpus/links.md",
        source_format="markdown_links",
        original_url="https://example.com/a",
        row_number=10,
    )

    _inserted, second_id = repository.insert_url_record(
        normalize_url("https://docs.example.org/b"),
        source_file="/private/corpus/notion_second_brain_links.csv",
    )
    repository.insert_source_occurrence(
        url_record_id=second_id,
        source_file="/private/corpus/notion_second_brain_links.csv",
        source_format="csv_url_export",
        original_url="https://docs.example.org/b",
        row_number=2,
    )
    repository.insert_source_occurrence(
        url_record_id=second_id,
        source_file="/private/corpus/links.md",
        source_format="markdown_links",
        original_url="https://docs.example.org/b",
        row_number=11,
    )

    _inserted, third_id = repository.insert_url_record(
        normalize_url("https://example.com/c"),
        source_file="/private/corpus/master_url_database.csv",
    )
    repository.insert_source_occurrence(
        url_record_id=third_id,
        source_file="/private/corpus/master_url_database.csv",
        source_format="csv_master_url_database",
        original_url="https://example.com/c",
        row_number=3,
    )

    repository.update_review_status(second_id, "reviewed")
    repository.insert_ai_enrichment(
        run_id="run-one",
        url_record_id=first_id,
        provider="mock",
        model="mock-local-v1",
        prompt_version="url_metadata_v1",
        input_hash="hash-one",
        status="pending_review",
        output_json="{}",
    )
    repository.insert_ai_enrichment(
        run_id="run-two",
        url_record_id=third_id,
        provider="mock",
        model="mock-local-v1",
        prompt_version="url_metadata_v1",
        input_hash="hash-two",
        status="approved",
        output_json="{}",
    )
    repository.record_ingest_run(
        run_id="ingest-one",
        source_file="/private/corpus/master_url_database.csv",
        input_count=3,
        valid_count=3,
        inserted_count=3,
        duplicate_count=0,
        malformed_count=0,
        failed_count=0,
        status="completed",
        error_class=None,
        duration_ms=1,
    )
    repository.record_ingest_run(
        run_id="ingest-two",
        source_file="/private/corpus/links.md",
        input_count=3,
        valid_count=2,
        inserted_count=0,
        duplicate_count=2,
        malformed_count=1,
        failed_count=1,
        status="completed_with_errors",
        error_class="malformed_url",
        duration_ms=1,
    )
    return repository
