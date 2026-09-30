from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from url_kb.ingest.dedupe import dedupe_normalized
from url_kb.ingest.parser import URLRowError, parse_url_csv
from url_kb.storage.sqlite_repo import SQLiteURLRepository


@dataclass(frozen=True)
class IngestBatchResult:
    run_id: str
    source_file: str
    input_count: int
    valid_count: int
    inserted_count: int
    duplicate_count: int
    malformed_count: int
    failed_count: int
    status: str
    duration_ms: int
    errors: list[URLRowError]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["errors"] = [asdict(error) for error in self.errors]
        return data


def ingest_batch(csv_path: Path, repository: SQLiteURLRepository) -> IngestBatchResult:
    repository.initialize()
    source_file = str(csv_path)
    run_id = str(uuid4())
    started_at = perf_counter()

    parsed = parse_url_csv(csv_path)
    unique_urls = dedupe_normalized(parsed.valid)
    batch_duplicate_count = len(parsed.records) - len(unique_urls)
    inserted_count = 0
    existing_duplicate_count = 0
    seen_batch_canonical_urls: set[str] = set()

    for record in parsed.records:
        url = record.normalized_url
        is_batch_duplicate = url.canonical_url in seen_batch_canonical_urls
        if not is_batch_duplicate:
            seen_batch_canonical_urls.add(url.canonical_url)

        inserted, record_id = repository.insert_url_record(
            url,
            source_file=source_file,
            title=record.original_label,
            original_label=record.original_label,
            source_type=record.source_type,
            raw_imported_status=record.raw_imported_status,
        )
        if inserted:
            inserted_count += 1
        elif not is_batch_duplicate:
            existing_duplicate_count += 1

        repository.insert_source_occurrence(
            url_record_id=record_id,
            source_file=source_file,
            source_format="csv_url_column",
            original_url=url.original_url,
            original_label=record.original_label,
            row_number=record.row_number,
            raw_imported_status=record.raw_imported_status,
        )

    malformed_count = len(parsed.errors)
    failed_count = malformed_count
    duplicate_count = batch_duplicate_count + existing_duplicate_count
    duration_ms = int((perf_counter() - started_at) * 1000)
    status = "completed_with_errors" if failed_count else "completed"

    repository.record_ingest_run(
        run_id=run_id,
        source_file=source_file,
        input_count=len(parsed.valid) + malformed_count,
        valid_count=len(parsed.valid),
        inserted_count=inserted_count,
        duplicate_count=duplicate_count,
        malformed_count=malformed_count,
        failed_count=failed_count,
        status=status,
        error_class="malformed_url" if malformed_count else None,
        duration_ms=duration_ms,
    )

    return IngestBatchResult(
        run_id=run_id,
        source_file=source_file,
        input_count=len(parsed.valid) + malformed_count,
        valid_count=len(parsed.valid),
        inserted_count=inserted_count,
        duplicate_count=duplicate_count,
        malformed_count=malformed_count,
        failed_count=failed_count,
        status=status,
        duration_ms=duration_ms,
        errors=parsed.errors,
    )
