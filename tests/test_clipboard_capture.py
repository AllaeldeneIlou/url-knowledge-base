from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from url_kb.ingest.clipboard import (
    CLIPBOARD_SOURCE_FORMAT,
    DEFAULT_CLIPBOARD_SOURCE_TYPE,
    ingest_clipboard_export,
    parse_clipboard_export,
)
from url_kb.storage.sqlite_repo import SQLiteURLRepository
from url_kb.web.app import create_app

SCRUBBED_PASTE = """
agentic AI + Agentic dev

[Vector DB vs Graph DB](https://video.example/watch?v=abc)
[Search Notes](https://search.example/search?q=agents) and [Workflow Patterns](https://blog.example/patterns)
![Diagram](https://images.example/diagram.png)
Bare link: https://docs.example.com/guide).
[Broken](not-a-url)
"""


def test_parse_clipboard_markdown_links_with_labels_and_inferred_title():
    result = parse_clipboard_export(SCRUBBED_PASTE)

    assert result.batch_title == "agentic AI + Agentic dev"
    assert result.source_type == DEFAULT_CLIPBOARD_SOURCE_TYPE
    assert result.source_file.startswith("clipboard:agentic-ai-agentic-dev:")
    assert result.valid_count == 4
    assert result.malformed_count == 1
    assert [record.original_label for record in result.parsed_rows.records[:3]] == [
        "Vector DB vs Graph DB",
        "Search Notes",
        "Workflow Patterns",
    ]
    assert "images.example" not in {record.domain for record in result.records}
    assert result.parsed_rows.records[-1].normalized_url.canonical_url == (
        "https://docs.example.com/guide"
    )
    assert result.error_reason_counts == {"URL must use http or https": 1}


def test_parse_clipboard_multiple_links_preserves_line_and_block_numbers():
    result = parse_clipboard_export(
        "[One](https://one.example/a) text [Two](https://two.example/b)"
    )

    assert [(record.row_number, record.block_number) for record in result.records] == [
        (1, 1),
        (1, 2),
    ]


def test_clipboard_preview_does_not_write_records(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")
    repository.initialize()

    preview = parse_clipboard_export(SCRUBBED_PASTE)

    assert preview.valid_count == 4
    assert repository.count_url_records() == 0
    assert repository.count_source_occurrences() == 0


def test_ingest_clipboard_writes_records_occurrences_and_is_idempotent(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    parsed, first_result = ingest_clipboard_export(SCRUBBED_PASTE, repository)
    first_occurrence_count = repository.count_source_occurrences()
    _parsed_again, second_result = ingest_clipboard_export(SCRUBBED_PASTE, repository)

    assert first_result.inserted_count == 4
    assert first_result.duplicate_count == 0
    assert first_result.failed_count == 1
    assert second_result.inserted_count == 0
    assert second_result.duplicate_count == 4
    assert second_result.failed_count == 1
    assert repository.count_url_records() == 4
    assert repository.count_source_occurrences() == first_occurrence_count

    occurrences = repository.list_source_occurrences()
    assert len(occurrences) == 4
    assert {occurrence.source_file for occurrence in occurrences} == {parsed.source_file}
    assert {occurrence.source_format for occurrence in occurrences} == {
        CLIPBOARD_SOURCE_FORMAT
    }
    assert {occurrence.source_section for occurrence in occurrences} == {
        "agentic AI + Agentic dev"
    }
    assert {occurrence.source_type for occurrence in occurrences} == {
        DEFAULT_CLIPBOARD_SOURCE_TYPE
    }
    assert {(occurrence.row_number, occurrence.block_number) for occurrence in occurrences} == {
        (3, 1),
        (4, 1),
        (4, 2),
        (6, 1),
    }
    assert {occurrence.raw_imported_status for occurrence in occurrences} == {"captured"}


def test_capture_page_loads_and_keeps_footer(tmp_path: Path):
    client = _client(tmp_path / "url_kb.sqlite3")

    response = client.get("/capture")

    assert response.status_code == 200
    assert "Clipboard Capture" in response.text
    assert "© Allaeldene Ilou" in response.text


def test_capture_preview_renders_parsed_result_without_writing(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    client = _client(database_path)

    response = client.post(
        "/capture",
        data={
            "action": "preview",
            "batch_title": "",
            "source_type": DEFAULT_CLIPBOARD_SOURCE_TYPE,
            "pasted_text": SCRUBBED_PASTE,
        },
    )

    assert response.status_code == 200
    assert "Preview" in response.text
    assert "video.example" in response.text
    assert '<td class="mono">images.example</td>' not in response.text
    assert "URL must use http or https" in response.text
    repository = SQLiteURLRepository(database_path)
    repository.initialize()
    assert repository.count_url_records() == 0


def test_capture_ingest_writes_records_and_renders_summary(tmp_path: Path):
    database_path = tmp_path / "url_kb.sqlite3"
    client = _client(database_path)

    response = client.post(
        "/capture",
        data={
            "action": "ingest",
            "batch_title": "Scrubbed batch",
            "source_type": DEFAULT_CLIPBOARD_SOURCE_TYPE,
            "pasted_text": SCRUBBED_PASTE,
        },
    )

    assert response.status_code == 200
    assert "Ingest Summary" in response.text
    assert "completed_with_errors" in response.text
    assert "Scrubbed batch" in response.text
    repository = SQLiteURLRepository(database_path)
    assert repository.count_url_records() == 4
    assert repository.count_source_occurrences() == 4


def _client(database_path: Path) -> TestClient:
    return TestClient(create_app(f"sqlite:///{database_path}"))
