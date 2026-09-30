from __future__ import annotations

from dataclasses import asdict, dataclass

from url_kb.storage.sqlite_repo import SQLiteURLRepository, StoredURLRecord


class URLRecordNotFoundError(LookupError):
    """Raised when a persisted URL record cannot be found."""


@dataclass(frozen=True)
class SearchSourcesResult:
    count: int
    records: list[StoredURLRecord]

    def to_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "records": [asdict(record) for record in self.records],
        }


@dataclass(frozen=True)
class UpdateReviewStatusResult:
    record: StoredURLRecord

    def to_dict(self) -> dict[str, object]:
        return {"record": asdict(self.record)}


def search_sources(
    repository: SQLiteURLRepository,
    *,
    query: str | None = None,
    domain: str | None = None,
    review_status: str | None = None,
) -> SearchSourcesResult:
    repository.initialize()
    records = repository.search_url_records(
        query=query,
        domain=domain,
        review_status=review_status,
    )
    return SearchSourcesResult(count=len(records), records=records)


def update_review_status(
    repository: SQLiteURLRepository,
    *,
    record_id: int,
    review_status: str,
) -> UpdateReviewStatusResult:
    repository.initialize()
    record = repository.update_review_status(record_id, review_status)
    if record is None:
        raise URLRecordNotFoundError(f"URL record not found: {record_id}")

    return UpdateReviewStatusResult(record=record)
