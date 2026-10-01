from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from url_kb.ingest.normalize import normalize_url
from url_kb.storage.sqlite_repo import SQLiteURLRepository
from url_kb.web.app import create_app


def test_overview_page_loads_metrics_and_footer(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    _seed_web_repository(database_path)
    client = _client(database_path)

    response = client.get("/")

    assert response.status_code == 200
    assert "Corpus Metrics" in response.text
    assert "URL records" in response.text
    assert "3" in response.text
    assert "© Allaeldene Ilou" in response.text


def test_sources_page_filters_records(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    _seed_web_repository(database_path)
    client = _client(database_path)

    response = client.get("/sources", params={"query": "python"})

    assert response.status_code == 200
    assert "docs.python.org" in response.text
    assert "FastAPI Docs" not in response.text


def test_record_detail_page_shows_provenance_and_enrichment_sections(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    ids = _seed_web_repository(database_path)
    client = _client(database_path)

    response = client.get(f"/sources/{ids['python_record_id']}")

    assert response.status_code == 200
    assert "URL Record" in response.text
    assert "Source Occurrences" in response.text
    assert "csv_master_url_database" in response.text
    assert "markdown_links" in response.text
    assert "Enrichment Drafts" in response.text
    assert "Mock draft metadata for Python documentation." in response.text
    assert "URL record review status is separate from enrichment review status" in response.text


def test_enrichments_page_lists_pending_drafts(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    _seed_web_repository(database_path)
    client = _client(database_path)

    response = client.get("/enrichments", params={"status": "pending_review"})

    assert response.status_code == 200
    assert "Enrichment Review" in response.text
    assert "docs.python.org" in response.text
    assert "FastAPI Docs" not in response.text


def test_enrichment_review_forms_update_status_and_note_only(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    ids = _seed_web_repository(database_path)
    repository = SQLiteURLRepository(database_path)
    before_review_status = repository.get_url_record(ids["python_record_id"]).review_status
    client = _client(database_path)

    approve_response = client.post(
        f"/enrichments/{ids['python_enrichment_id']}/review",
        data={
            "status": "approved",
            "note": "Looks accurate.",
            "next": "/enrichments",
        },
        follow_redirects=False,
    )

    assert approve_response.status_code == 303
    enrichment = repository.list_ai_enrichments_for_url_record_id(ids["python_record_id"])[0]
    assert enrichment.status == "approved"
    assert enrichment.reviewer_note == "Looks accurate."
    assert repository.get_url_record(ids["python_record_id"]).review_status == before_review_status

    reject_response = client.post(
        f"/enrichments/{ids['python_enrichment_id']}/review",
        data={
            "status": "rejected",
            "note": "Topic tags are broad.",
            "next": "/enrichments",
        },
        follow_redirects=False,
    )

    assert reject_response.status_code == 303
    enrichment = repository.list_ai_enrichments_for_url_record_id(ids["python_record_id"])[0]
    assert enrichment.status == "rejected"
    assert enrichment.reviewer_note == "Topic tags are broad."
    assert repository.get_url_record(ids["python_record_id"]).review_status == before_review_status


def _client(database_path: Path) -> TestClient:
    return TestClient(create_app(f"sqlite:///{database_path}"))


def _seed_web_repository(database_path: Path) -> dict[str, int]:
    repository = SQLiteURLRepository(database_path)
    repository.initialize()
    _inserted, python_id = repository.insert_url_record(
        normalize_url("https://docs.python.org/3/"),
        source_file="/private/corpus/master_url_database.csv",
        title="Python Docs",
        original_label="Python Docs",
        source_type="documentation",
        raw_imported_status="TO_REVIEW",
    )
    repository.insert_source_occurrence(
        url_record_id=python_id,
        source_file="/private/corpus/master_url_database.csv",
        source_format="csv_master_url_database",
        original_url="https://docs.python.org/3/",
        original_label="Python Docs",
        row_number=2,
    )
    repository.insert_source_occurrence(
        url_record_id=python_id,
        source_file="/private/corpus/links.md",
        source_format="markdown_links",
        original_url="https://docs.python.org/3/",
        original_label="Python Docs",
        source_section="Language docs",
        row_number=8,
        block_number=1,
    )
    python_enrichment_id = repository.insert_ai_enrichment(
        run_id="run-python",
        url_record_id=python_id,
        provider="mock",
        model="mock-local-v1",
        prompt_version="url_metadata_v1",
        input_hash="hash-python",
        status="pending_review",
        output_json=(
            '{"summary":"Mock draft metadata for Python documentation.",'
            '"topics":["python","docs"],"content_type":"documentation","confidence":0.5}'
        ),
        token_input_count=12,
        token_output_count=18,
        estimated_cost_usd=0.0,
    )

    _inserted, fastapi_id = repository.insert_url_record(
        normalize_url("https://fastapi.tiangolo.com/"),
        source_file="/private/corpus/notion_second_brain_links.csv",
        title="FastAPI Docs",
        source_type="documentation",
    )
    repository.insert_source_occurrence(
        url_record_id=fastapi_id,
        source_file="/private/corpus/notion_second_brain_links.csv",
        source_format="csv_url_export",
        original_url="https://fastapi.tiangolo.com/",
        original_label="FastAPI Docs",
        row_number=3,
    )
    repository.insert_ai_enrichment(
        run_id="run-fastapi",
        url_record_id=fastapi_id,
        provider="mock",
        model="mock-local-v1",
        prompt_version="url_metadata_v1",
        input_hash="hash-fastapi",
        status="approved",
        output_json='{"summary":"Mock draft metadata for FastAPI."}',
    )

    _inserted, sqlite_id = repository.insert_url_record(
        normalize_url("https://www.sqlite.org/"),
        source_file="/private/corpus/links.md",
        title="SQLite",
    )
    repository.insert_source_occurrence(
        url_record_id=sqlite_id,
        source_file="/private/corpus/links.md",
        source_format="markdown_links",
        original_url="https://www.sqlite.org/",
        original_label="SQLite",
        row_number=4,
    )
    return {
        "python_record_id": python_id,
        "python_enrichment_id": python_enrichment_id,
    }
