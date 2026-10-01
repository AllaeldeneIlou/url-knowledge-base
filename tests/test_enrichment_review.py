from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from url_kb.enrich.service import (
    EnrichmentNotFoundError,
    enrich_sources,
    list_enrichments,
    review_enrichment,
    show_enrichment,
)
from url_kb.ingest.normalize import normalize_url
from url_kb.storage.sqlite_repo import SQLiteURLRepository


def test_pending_enrichment_drafts_can_be_listed(tmp_path: Path):
    repository = _seed_enriched_repository(tmp_path)

    result = list_enrichments(repository, status="pending_review", provider="mock", limit=10)

    payload = result.to_dict()
    assert payload["count"] == 1
    assert payload["enrichments"][0]["canonical_url"] == (
        "https://docs.python.org/3/library/urllib.parse.html"
    )
    assert payload["enrichments"][0]["provider"] == "mock"
    assert payload["enrichments"][0]["status"] == "pending_review"
    assert payload["enrichments"][0]["created_at"]


def test_enrichment_detail_includes_url_metadata_and_output_json(tmp_path: Path):
    repository = _seed_enriched_repository(tmp_path)
    enrichment_id = repository.list_ai_enrichments()[0].id

    result = show_enrichment(repository, enrichment_id=enrichment_id)

    payload = result.to_dict()["enrichment"]
    assert payload["id"] == enrichment_id
    assert payload["output"]["summary"] == (
        "Mock draft metadata for Python urllib.parse documentation."
    )
    assert payload["url_record"]["canonical_url"] == (
        "https://docs.python.org/3/library/urllib.parse.html"
    )
    assert payload["url_record"]["title"] == "Python urllib.parse documentation"


def test_approving_enrichment_changes_only_enrichment_review_fields(tmp_path: Path):
    repository = _seed_enriched_repository(tmp_path)
    enrichment_id = repository.list_ai_enrichments()[0].id
    before_records = [asdict(record) for record in repository.list_url_records()]

    result = review_enrichment(
        repository,
        enrichment_id=enrichment_id,
        status="approved",
        reviewer_note="Looks accurate.",
        reviewed_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    after_records = [asdict(record) for record in repository.list_url_records()]
    payload = result.to_dict()
    assert before_records == after_records
    assert payload == {
        "id": enrichment_id,
        "previous_status": "pending_review",
        "new_status": "approved",
        "reviewer_note": "Looks accurate.",
        "reviewed_at": "2026-01-02T03:04:05+00:00",
    }


def test_rejecting_enrichment_stores_reviewer_note(tmp_path: Path):
    repository = _seed_enriched_repository(tmp_path)
    enrichment_id = repository.list_ai_enrichments()[0].id

    review_enrichment(
        repository,
        enrichment_id=enrichment_id,
        status="rejected",
        reviewer_note="Topic tags are too broad.",
        reviewed_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    enrichment = repository.list_ai_enrichments()[0]
    assert enrichment.status == "rejected"
    assert enrichment.reviewer_note == "Topic tags are too broad."
    assert enrichment.reviewed_at == "2026-01-02T03:04:05+00:00"


def test_reviewed_enrichment_can_be_updated_with_new_note(tmp_path: Path):
    repository = _seed_enriched_repository(tmp_path)
    enrichment_id = repository.list_ai_enrichments()[0].id
    review_enrichment(repository, enrichment_id=enrichment_id, status="approved")

    result = review_enrichment(
        repository,
        enrichment_id=enrichment_id,
        status="rejected",
        reviewer_note="Second pass found overly broad tags.",
    )

    payload = result.to_dict()
    assert payload["previous_status"] == "approved"
    assert payload["new_status"] == "rejected"
    assert payload["reviewer_note"] == "Second pass found overly broad tags."


def test_review_enrichment_rejects_invalid_status(tmp_path: Path):
    repository = _seed_enriched_repository(tmp_path)
    enrichment_id = repository.list_ai_enrichments()[0].id

    with pytest.raises(ValueError, match="enrichment review status must be one of"):
        review_enrichment(repository, enrichment_id=enrichment_id, status="maybe")


def test_review_enrichment_rejects_pending_review_as_decision(tmp_path: Path):
    repository = _seed_enriched_repository(tmp_path)
    enrichment_id = repository.list_ai_enrichments()[0].id

    with pytest.raises(ValueError, match="enrichment review decision must be one of"):
        review_enrichment(repository, enrichment_id=enrichment_id, status="pending_review")


def test_missing_enrichment_id_returns_clear_error_path(tmp_path: Path):
    repository = _seed_enriched_repository(tmp_path)

    with pytest.raises(EnrichmentNotFoundError, match="AI enrichment not found: 999"):
        show_enrichment(repository, enrichment_id=999)

    with pytest.raises(EnrichmentNotFoundError, match="AI enrichment not found: 999"):
        review_enrichment(repository, enrichment_id=999, status="approved")


def test_enrichment_review_cli_outputs_json(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    repository = _seed_enriched_repository(tmp_path, database_path=database_path)
    enrichment_id = repository.list_ai_enrichments()[0].id

    list_completed = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "url_kb.cli",
            "list_enrichments",
            "--status",
            "pending_review",
            "--database-url",
            f"sqlite:///{database_path}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    show_completed = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "url_kb.cli",
            "show_enrichment",
            str(enrichment_id),
            "--database-url",
            f"sqlite:///{database_path}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    review_completed = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "url_kb.cli",
            "review_enrichment",
            str(enrichment_id),
            "approved",
            "--note",
            "Looks accurate.",
            "--database-url",
            f"sqlite:///{database_path}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    list_payload = json.loads(list_completed.stdout)
    show_payload = json.loads(show_completed.stdout)
    review_payload = json.loads(review_completed.stdout)
    assert list_payload["count"] == 1
    assert show_payload["enrichment"]["id"] == enrichment_id
    assert review_payload["previous_status"] == "pending_review"
    assert review_payload["new_status"] == "approved"
    assert review_payload["reviewer_note"] == "Looks accurate."


def _seed_enriched_repository(
    tmp_path: Path, database_path: Path | None = None
) -> SQLiteURLRepository:
    repository = SQLiteURLRepository(database_path or tmp_path / "url_kb.sqlite3")
    repository.initialize()
    _inserted, record_id = repository.insert_url_record(
        normalize_url("https://docs.python.org/3/library/urllib.parse.html"),
        source_file="samples/public_urls.csv",
        title="Python urllib.parse documentation",
        original_label="Python urllib.parse documentation",
        source_type="public_sample",
        raw_imported_status="TO_REVIEW",
    )
    repository.insert_source_occurrence(
        url_record_id=record_id,
        source_file="samples/public_urls.csv",
        source_format="csv_url_column",
        original_url="https://docs.python.org/3/library/urllib.parse.html",
        original_label="Python urllib.parse documentation",
        row_number=2,
        raw_imported_status="TO_REVIEW",
    )
    enrich_sources(repository, query="python", provider_name="mock")
    return repository
