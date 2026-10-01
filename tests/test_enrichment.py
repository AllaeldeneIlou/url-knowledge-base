from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from url_kb.enrich.providers import (
    DEFAULT_MOCK_MODEL,
    DEFAULT_PROMPT_VERSION,
    EnrichmentInput,
    MockEnrichmentProvider,
)
from url_kb.enrich.service import enrich_sources
from url_kb.ingest.normalize import normalize_url
from url_kb.storage.sqlite_repo import SQLiteURLRepository


def test_mock_provider_is_deterministic(tmp_path: Path):
    repository = _seed_repository(tmp_path)
    record = repository.list_url_records()[0]
    provider = MockEnrichmentProvider()
    enrichment_input = EnrichmentInput.from_record(record, DEFAULT_PROMPT_VERSION)

    first = provider.enrich(enrichment_input, model=DEFAULT_MOCK_MODEL)
    second = provider.enrich(enrichment_input, model=DEFAULT_MOCK_MODEL)

    assert first == second
    assert first.output.to_dict()["content_type"] == "public_sample"


def test_enrich_sources_writes_draft_rows_without_mutating_url_records(tmp_path: Path):
    repository = _seed_repository(tmp_path)
    before_records = [asdict(record) for record in repository.list_url_records()]

    result = enrich_sources(repository, query="python", provider_name="mock")

    after_records = [asdict(record) for record in repository.list_url_records()]
    enrichments = repository.list_ai_enrichments()
    assert before_records == after_records
    assert result.matching_record_count == 1
    assert result.enriched_record_count == 1
    assert result.enrichment_ids == [enrichments[0].id]
    assert result.run_id == enrichments[0].run_id
    assert enrichments[0].url_record_id == before_records[0]["id"]
    assert enrichments[0].status == "pending_review"


def test_dry_run_writes_no_enrichment_rows(tmp_path: Path):
    repository = _seed_repository(tmp_path)

    result = enrich_sources(repository, query="python", provider_name="mock", dry_run=True)

    assert result.dry_run is True
    assert result.selected_record_count == 1
    assert result.enriched_record_count == 0
    assert result.enrichment_ids == []
    assert repository.count_ai_enrichments() == 0


def test_limit_bounds_selected_records(tmp_path: Path):
    repository = _seed_repository(tmp_path)

    result = enrich_sources(repository, provider_name="mock", limit=2)

    assert result.matching_record_count == 3
    assert result.selected_record_count == 2
    assert result.enriched_record_count == 2
    assert result.skipped_record_count == 1
    assert repository.count_ai_enrichments() == 2


def test_enrichment_stores_provider_model_prompt_status_and_output_json(tmp_path: Path):
    repository = _seed_repository(tmp_path)

    enrich_sources(
        repository,
        query="python",
        provider_name="mock",
        model="mock-interview-v1",
        prompt_version="url_metadata_test",
    )

    enrichment = repository.list_ai_enrichments()[0]
    output = json.loads(enrichment.output_json)
    assert enrichment.run_id
    assert enrichment.provider == "mock"
    assert enrichment.model == "mock-interview-v1"
    assert enrichment.prompt_version == "url_metadata_test"
    assert enrichment.status == "pending_review"
    assert enrichment.input_hash
    assert enrichment.token_input_count is not None
    assert enrichment.token_output_count is not None
    assert enrichment.estimated_cost_usd == 0.0
    assert enrichment.error_class is None
    assert output == {
        "confidence": 0.5,
        "content_type": "public_sample",
        "notes": (
            "Deterministic mock enrichment only; pending human review and not based on "
            "fetched page content."
        ),
        "summary": "Mock draft metadata for Python urllib.parse documentation.",
        "topics": ["public", "sample", "docs", "python", "org"],
    }


def test_enrich_sources_rejects_invalid_limit(tmp_path: Path):
    repository = _seed_repository(tmp_path)

    with pytest.raises(ValueError, match="limit must be at least 1"):
        enrich_sources(repository, limit=0)


def test_enrich_sources_cli_writes_mock_enrichments(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    _seed_repository(tmp_path, database_path=database_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "url_kb.cli",
            "enrich_sources",
            "--query",
            "python",
            "--provider",
            "mock",
            "--limit",
            "3",
            "--database-url",
            f"sqlite:///{database_path}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    repository = SQLiteURLRepository(database_path)
    repository.initialize()
    enrichment = repository.list_ai_enrichments()[0]
    assert payload["run_id"] == enrichment.run_id
    assert payload["provider"] == "mock"
    assert payload["selected_record_count"] == 1
    assert payload["enriched_record_count"] == 1
    assert repository.count_ai_enrichments() == 1


def _seed_repository(
    tmp_path: Path, database_path: Path | None = None
) -> SQLiteURLRepository:
    repository = SQLiteURLRepository(database_path or tmp_path / "url_kb.sqlite3")
    repository.initialize()
    _inserted, first_id = repository.insert_url_record(
        normalize_url("https://docs.python.org/3/library/urllib.parse.html"),
        source_file="samples/public_urls.csv",
        title="Python urllib.parse documentation",
        original_label="Python urllib.parse documentation",
        source_type="public_sample",
        raw_imported_status="TO_REVIEW",
    )
    repository.insert_source_occurrence(
        url_record_id=first_id,
        source_file="samples/public_urls.csv",
        source_format="csv_url_column",
        original_url="https://docs.python.org/3/library/urllib.parse.html",
        original_label="Python urllib.parse documentation",
        row_number=2,
        raw_imported_status="TO_REVIEW",
    )
    _inserted, second_id = repository.insert_url_record(
        normalize_url("https://fastapi.tiangolo.com/"),
        source_file="samples/public_urls.csv",
        title="FastAPI documentation",
        source_type="public_sample",
    )
    repository.insert_source_occurrence(
        url_record_id=second_id,
        source_file="samples/public_urls.csv",
        source_format="csv_url_column",
        original_url="https://fastapi.tiangolo.com/",
        row_number=3,
    )
    _inserted, third_id = repository.insert_url_record(
        normalize_url("https://www.sqlite.org/fts5.html"),
        source_file="samples/public_urls.csv",
    )
    repository.insert_source_occurrence(
        url_record_id=third_id,
        source_file="samples/public_urls.csv",
        source_format="csv_url_column",
        original_url="https://www.sqlite.org/fts5.html",
        row_number=4,
    )
    return repository
