from pathlib import Path

from url_kb.ingest.normalize import normalize_url
from url_kb.storage.sqlite_repo import SQLiteURLRepository, parse_sqlite_database_url


def test_database_initialization_creates_expected_tables(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    repository.initialize()

    assert repository.count_url_records() == 0
    assert repository.count_source_occurrences() == 0
    assert repository.list_ingest_runs() == []


def test_insert_url_record_persists_record(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")
    repository.initialize()

    inserted, record_id = repository.insert_url_record(
        normalize_url("https://example.com/path"),
        source_file="sample.csv",
    )

    records = repository.list_url_records()
    assert inserted is True
    assert record_id == records[0].id
    assert records[0].canonical_url == "https://example.com/path"
    assert records[0].domain == "example.com"
    assert records[0].review_status == "pending_review"
    assert records[0].title is None
    assert records[0].original_label is None
    assert records[0].source_type is None
    assert records[0].raw_imported_status is None


def test_insert_url_record_persists_optional_metadata(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")
    repository.initialize()

    repository.insert_url_record(
        normalize_url("https://example.com/path"),
        source_file="sample.csv",
        title="Example Title",
        original_label="Example Label",
        source_type="documentation",
        raw_imported_status="IMPORTED",
    )

    record = repository.list_url_records()[0]
    assert record.title == "Example Title"
    assert record.original_label == "Example Label"
    assert record.source_type == "documentation"
    assert record.raw_imported_status == "IMPORTED"


def test_insert_url_record_skips_existing_duplicate(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")
    repository.initialize()

    first_inserted, first_id = repository.insert_url_record(
        normalize_url("https://example.com/path#fragment"),
        source_file="sample.csv",
    )
    duplicate_inserted, duplicate_id = repository.insert_url_record(
        normalize_url("https://example.com/path"),
        source_file="sample.csv",
    )

    assert first_inserted is True
    assert duplicate_inserted is False
    assert duplicate_id == first_id
    assert repository.count_url_records() == 1


def test_insert_source_occurrence_persists_and_dedupes_same_csv_row(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")
    repository.initialize()
    _inserted, record_id = repository.insert_url_record(
        normalize_url("https://example.com/path"),
        source_file="sample.csv",
    )

    first_inserted, first_id = repository.insert_source_occurrence(
        url_record_id=record_id,
        source_file="sample.csv",
        source_format="csv_url_column",
        original_url="https://example.com/path",
        original_label="Example",
        row_number=2,
    )
    duplicate_inserted, duplicate_id = repository.insert_source_occurrence(
        url_record_id=record_id,
        source_file="sample.csv",
        source_format="csv_url_column",
        original_url="https://example.com/path",
        original_label="Example",
        row_number=2,
    )

    occurrences = repository.list_source_occurrences()
    assert first_inserted is True
    assert duplicate_inserted is False
    assert duplicate_id == first_id
    assert len(occurrences) == 1
    assert occurrences[0].url_record_id == record_id
    assert occurrences[0].source_format == "csv_url_column"
    assert occurrences[0].original_label == "Example"
    assert occurrences[0].row_number == 2


def test_insert_source_occurrence_dedupes_when_row_number_is_null(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")
    repository.initialize()
    _inserted, record_id = repository.insert_url_record(
        normalize_url("https://example.com/path"),
        source_file="sample.md",
    )

    first_inserted, first_id = repository.insert_source_occurrence(
        url_record_id=record_id,
        source_file="sample.md",
        source_format="markdown_links",
        original_url="https://example.com/path",
        original_label="Example",
        row_number=None,
    )
    duplicate_inserted, duplicate_id = repository.insert_source_occurrence(
        url_record_id=record_id,
        source_file="sample.md",
        source_format="markdown_links",
        original_url="https://example.com/path",
        original_label="Example",
        row_number=None,
    )

    assert first_inserted is True
    assert duplicate_inserted is False
    assert duplicate_id == first_id
    assert repository.count_source_occurrences() == 1


def test_parse_sqlite_database_url_supports_relative_project_path():
    assert parse_sqlite_database_url("sqlite:///./data/url_kb.sqlite3") == "./data/url_kb.sqlite3"


def test_parse_sqlite_database_url_supports_memory_database():
    assert parse_sqlite_database_url("sqlite:///:memory:") == ":memory:"


def test_parse_sqlite_database_url_supports_four_slash_absolute_path():
    assert parse_sqlite_database_url("sqlite:////tmp/url_kb.sqlite3") == "/tmp/url_kb.sqlite3"


def test_memory_database_uses_one_repository_connection():
    repository = SQLiteURLRepository.from_database_url("sqlite:///:memory:")
    repository.initialize()

    inserted, _record_id = repository.insert_url_record(
        normalize_url("https://example.com/memory"),
        source_file="memory.csv",
    )

    assert inserted is True
    assert repository.count_url_records() == 1
