from pathlib import Path

import pytest

from url_kb.ingest.normalize import normalize_url
from url_kb.search.service import URLRecordNotFoundError, search_sources, update_review_status
from url_kb.storage.sqlite_repo import SQLiteURLRepository


def test_search_sources_by_keyword(tmp_path: Path):
    repository = _seed_repository(tmp_path)

    result = search_sources(repository, query="python")

    assert result.count == 1
    assert result.records[0].domain == "docs.python.org"


def test_search_sources_by_domain(tmp_path: Path):
    repository = _seed_repository(tmp_path)

    result = search_sources(repository, domain="fastapi.tiangolo.com")

    assert result.count == 1
    assert result.records[0].canonical_url == "https://fastapi.tiangolo.com/"


def test_search_sources_by_review_status(tmp_path: Path):
    repository = _seed_repository(tmp_path)
    first_record = repository.list_url_records()[0]
    update_review_status(repository, record_id=first_record.id, review_status="reviewed")

    result = search_sources(repository, review_status="reviewed")

    assert result.count == 1
    assert result.records[0].id == first_record.id
    assert result.records[0].review_status == "reviewed"


def test_update_review_status_accepts_valid_status(tmp_path: Path):
    repository = _seed_repository(tmp_path)
    first_record = repository.list_url_records()[0]

    result = update_review_status(repository, record_id=first_record.id, review_status="rejected")

    assert result.record.id == first_record.id
    assert result.record.review_status == "rejected"


def test_update_review_status_rejects_invalid_status(tmp_path: Path):
    repository = _seed_repository(tmp_path)
    first_record = repository.list_url_records()[0]

    with pytest.raises(ValueError, match="review_status must be one of"):
        update_review_status(repository, record_id=first_record.id, review_status="archived")


def test_update_review_status_rejects_missing_record_id(tmp_path: Path):
    repository = _seed_repository(tmp_path)

    with pytest.raises(URLRecordNotFoundError, match="URL record not found"):
        update_review_status(repository, record_id=999, review_status="reviewed")


def _seed_repository(tmp_path: Path) -> SQLiteURLRepository:
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")
    repository.initialize()
    repository.insert_url_record(
        normalize_url("https://docs.python.org/3/library/sqlite3.html"),
        source_file="samples/python.csv",
    )
    repository.insert_url_record(
        normalize_url("https://fastapi.tiangolo.com/"),
        source_file="samples/fastapi.csv",
    )
    repository.insert_url_record(
        normalize_url("https://www.sqlite.org/fts5.html"),
        source_file="samples/sqlite.csv",
    )
    return repository
