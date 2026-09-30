from pathlib import Path

from url_kb.ingest.normalize import normalize_url
from url_kb.storage.sqlite_repo import SQLiteURLRepository, parse_sqlite_database_url


def test_database_initialization_creates_expected_tables(tmp_path: Path):
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    repository.initialize()

    assert repository.count_url_records() == 0
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
