from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from url_kb.export.source_packet import export_source_packet
from url_kb.ingest.normalize import normalize_url
from url_kb.storage.sqlite_repo import SQLiteURLRepository


def test_export_source_packet_includes_url_metadata_and_provenance(tmp_path: Path):
    repository = _seed_repository(tmp_path)
    output_path = tmp_path / "packet.md"

    result = export_source_packet(
        repository,
        query="python",
        output_path=output_path,
        generated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    markdown = output_path.read_text(encoding="utf-8")
    assert result.record_count == 1
    assert "# URL Knowledge Base Source Packet" in markdown
    assert "Status: draft / pending human review" in markdown
    assert "Canonical URL: https://docs.python.org/3/library/urllib.parse.html" in markdown
    assert "Original URL: https://docs.python.org/3/library/urllib.parse.html" in markdown
    assert "Domain: docs.python.org" in markdown
    assert "Review status: pending_review" in markdown
    assert "Title: Python urllib.parse documentation" in markdown
    assert "Original label: Python urllib.parse documentation" in markdown
    assert "Source type: public_sample" in markdown
    assert "Raw imported status: TO_REVIEW" in markdown
    assert "Source file: samples/public_urls.csv" in markdown
    assert "Format: csv_url_column" in markdown
    assert "Row: 2" in markdown


def test_export_source_packet_renders_null_optional_fields_cleanly(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")
    repository.initialize()
    _inserted, record_id = repository.insert_url_record(
        normalize_url("https://example.com/no-title"),
        source_file="samples/nulls.csv",
    )
    repository.insert_source_occurrence(
        url_record_id=record_id,
        source_file="samples/nulls.csv",
        source_format="csv_url_column",
        original_url="https://example.com/no-title",
    )
    output_path = tmp_path / "packet.md"

    export_source_packet(repository, output_path=output_path)

    markdown = output_path.read_text(encoding="utf-8")
    assert "None" not in markdown
    assert "Title: N/A" in markdown
    assert "Original label: N/A" in markdown
    assert "Row: N/A" in markdown
    assert "Block: N/A" in markdown


def test_export_source_packet_empty_results_are_valid(tmp_path: Path):
    repository = _seed_repository(tmp_path)
    output_path = tmp_path / "empty.md"

    result = export_source_packet(repository, query="missing", output_path=output_path)

    markdown = output_path.read_text(encoding="utf-8")
    assert result.record_count == 0
    assert "Record count: 0" in markdown
    assert "No persisted URL records matched the selected filters." in markdown


def test_export_source_packet_cli_writes_requested_markdown_file(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    repository = _seed_repository(tmp_path, database_path=database_path)
    repository.initialize()
    output_path = tmp_path / "cli_packet.md"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "url_kb.cli",
            "export_source_packet",
            "--query",
            "python",
            "--output",
            str(output_path),
            "--database-url",
            f"sqlite:///{database_path}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["record_count"] == 1
    assert payload["output_path"] == str(output_path)
    assert output_path.exists()
    assert "Python urllib.parse documentation" in output_path.read_text(encoding="utf-8")


def _seed_repository(
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
    return repository
