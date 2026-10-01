from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from url_kb.ingest.normalize import NormalizedURL

REVIEW_STATUSES = frozenset({"pending_review", "reviewed", "rejected"})
ENRICHMENT_REVIEW_STATUSES = frozenset({"pending_review", "approved", "rejected"})


@dataclass(frozen=True)
class StoredURLRecord:
    id: int
    original_url: str
    canonical_url: str
    domain: str
    url_hash: str
    source_file: str
    review_status: str
    title: str | None = None
    original_label: str | None = None
    source_type: str | None = None
    raw_imported_status: str | None = None


@dataclass(frozen=True)
class StoredSourceOccurrence:
    id: int
    url_record_id: int
    source_file: str
    source_format: str
    original_url: str
    original_label: str | None
    source_section: str | None
    row_number: int | None
    block_number: int | None
    raw_imported_status: str | None


@dataclass(frozen=True)
class StoredIngestRun:
    id: int
    run_id: str
    source_file: str
    input_count: int
    valid_count: int
    inserted_count: int
    duplicate_count: int
    malformed_count: int
    failed_count: int
    status: str


@dataclass(frozen=True)
class URLRecordOccurrenceInput:
    url: NormalizedURL
    source_file: str
    source_format: str
    title: str | None = None
    original_label: str | None = None
    source_type: str | None = None
    raw_imported_status: str | None = None
    source_section: str | None = None
    row_number: int | None = None
    block_number: int | None = None


@dataclass(frozen=True)
class URLRecordOccurrenceInsertResult:
    inserted: bool
    record_id: int


@dataclass(frozen=True)
class StoredLatestIngestRun:
    id: int
    source_file: str
    input_count: int
    valid_count: int
    inserted_count: int
    duplicate_count: int
    malformed_count: int
    failed_count: int
    status: str
    created_at: str


@dataclass(frozen=True)
class MultiOccurrenceURLRecord:
    url_record_id: int
    domain: str
    occurrence_count: int


@dataclass(frozen=True)
class StoredAIEnrichment:
    id: int
    run_id: str
    url_record_id: int
    provider: str
    model: str
    prompt_version: str
    input_hash: str
    status: str
    output_json: str
    token_input_count: int | None
    token_output_count: int | None
    estimated_cost_usd: float | None
    error_class: str | None
    created_at: str
    reviewed_at: str | None
    reviewer_note: str | None


@dataclass(frozen=True)
class StoredAIEnrichmentWithURL:
    enrichment: StoredAIEnrichment
    url_record: StoredURLRecord


class SQLiteURLRepository:
    """Small sqlite3 repository for deterministic local persistence."""

    def __init__(self, database_path: Path | str):
        self.database_path = str(database_path)
        self._memory_connection: sqlite3.Connection | None = None

    @classmethod
    def from_database_url(cls, database_url: str) -> SQLiteURLRepository:
        return cls(parse_sqlite_database_url(database_url))

    def initialize(self) -> None:
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS url_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_url TEXT NOT NULL,
                    canonical_url TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL,
                    url_hash TEXT NOT NULL UNIQUE,
                    source_file TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'pending_review',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS ingest_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    source_file TEXT NOT NULL,
                    input_count INTEGER NOT NULL,
                    valid_count INTEGER NOT NULL,
                    inserted_count INTEGER NOT NULL,
                    duplicate_count INTEGER NOT NULL,
                    malformed_count INTEGER NOT NULL,
                    failed_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_class TEXT,
                    duration_ms INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS source_occurrences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_record_id INTEGER NOT NULL,
                    source_file TEXT NOT NULL,
                    source_format TEXT NOT NULL,
                    original_url TEXT NOT NULL,
                    original_label TEXT,
                    source_section TEXT,
                    row_number INTEGER,
                    block_number INTEGER,
                    raw_imported_status TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (url_record_id) REFERENCES url_records(id) ON DELETE CASCADE
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_source_occurrences_identity
                ON source_occurrences (
                    url_record_id,
                    source_file,
                    source_format,
                    COALESCE(row_number, -1),
                    COALESCE(block_number, -1),
                    original_url
                );

                CREATE TABLE IF NOT EXISTS ai_enrichments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    url_record_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_review',
                    output_json TEXT NOT NULL,
                    token_input_count INTEGER,
                    token_output_count INTEGER,
                    estimated_cost_usd REAL,
                    error_class TEXT,
                    reviewed_at TEXT,
                    reviewer_note TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (url_record_id) REFERENCES url_records(id) ON DELETE CASCADE
                );
                """
            )
            self._ensure_url_record_columns(connection)
            self._ensure_ai_enrichment_columns(connection)

    def insert_url_record(
        self,
        url: NormalizedURL,
        source_file: str,
        *,
        title: str | None = None,
        original_label: str | None = None,
        source_type: str | None = None,
        raw_imported_status: str | None = None,
    ) -> tuple[bool, int]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO url_records (
                    original_url,
                    canonical_url,
                    domain,
                    url_hash,
                    source_file,
                    title,
                    original_label,
                    source_type,
                    raw_imported_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    url.original_url,
                    url.canonical_url,
                    url.domain,
                    url.url_hash,
                    source_file,
                    title,
                    original_label,
                    source_type,
                    raw_imported_status,
                ),
            )

            if cursor.rowcount == 1:
                return True, int(cursor.lastrowid)

            existing_id = connection.execute(
                "SELECT id FROM url_records WHERE canonical_url = ? OR url_hash = ?",
                (url.canonical_url, url.url_hash),
            ).fetchone()["id"]
            return False, int(existing_id)

    def insert_source_occurrence(
        self,
        *,
        url_record_id: int,
        source_file: str,
        source_format: str,
        original_url: str,
        original_label: str | None = None,
        source_section: str | None = None,
        row_number: int | None = None,
        block_number: int | None = None,
        raw_imported_status: str | None = None,
    ) -> tuple[bool, int]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO source_occurrences (
                    url_record_id,
                    source_file,
                    source_format,
                    original_url,
                    original_label,
                    source_section,
                    row_number,
                    block_number,
                    raw_imported_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    url_record_id,
                    source_file,
                    source_format,
                    original_url,
                    original_label,
                    source_section,
                    row_number,
                    block_number,
                    raw_imported_status,
                ),
            )

            if cursor.rowcount == 1:
                return True, int(cursor.lastrowid)

            existing_id = connection.execute(
                """
                SELECT id
                FROM source_occurrences
                WHERE url_record_id = ?
                  AND source_file = ?
                  AND source_format = ?
                  AND COALESCE(row_number, -1) = COALESCE(?, -1)
                  AND COALESCE(block_number, -1) = COALESCE(?, -1)
                  AND original_url = ?
                """,
                (
                    url_record_id,
                    source_file,
                    source_format,
                    row_number,
                    block_number,
                    original_url,
                ),
            ).fetchone()["id"]
            return False, int(existing_id)

    def insert_url_records_with_occurrences(
        self, entries: list[URLRecordOccurrenceInput]
    ) -> list[URLRecordOccurrenceInsertResult]:
        results: list[URLRecordOccurrenceInsertResult] = []

        with self._connect() as connection:
            for entry in entries:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO url_records (
                        original_url,
                        canonical_url,
                        domain,
                        url_hash,
                        source_file,
                        title,
                        original_label,
                        source_type,
                        raw_imported_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.url.original_url,
                        entry.url.canonical_url,
                        entry.url.domain,
                        entry.url.url_hash,
                        entry.source_file,
                        entry.title,
                        entry.original_label,
                        entry.source_type,
                        entry.raw_imported_status,
                    ),
                )
                inserted = cursor.rowcount == 1
                if inserted:
                    record_id = int(cursor.lastrowid)
                else:
                    record_id = int(
                        connection.execute(
                            "SELECT id FROM url_records WHERE canonical_url = ? OR url_hash = ?",
                            (entry.url.canonical_url, entry.url.url_hash),
                        ).fetchone()["id"]
                    )

                connection.execute(
                    """
                    INSERT OR IGNORE INTO source_occurrences (
                        url_record_id,
                        source_file,
                        source_format,
                        original_url,
                        original_label,
                        source_section,
                        row_number,
                        block_number,
                        raw_imported_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        entry.source_file,
                        entry.source_format,
                        entry.url.original_url,
                        entry.original_label,
                        entry.source_section,
                        entry.row_number,
                        entry.block_number,
                        entry.raw_imported_status,
                    ),
                )
                results.append(
                    URLRecordOccurrenceInsertResult(
                        inserted=inserted,
                        record_id=record_id,
                    )
                )

        return results

    def record_ingest_run(
        self,
        *,
        run_id: str,
        source_file: str,
        input_count: int,
        valid_count: int,
        inserted_count: int,
        duplicate_count: int,
        malformed_count: int,
        failed_count: int,
        status: str,
        error_class: str | None,
        duration_ms: int,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ingest_runs (
                    run_id,
                    source_file,
                    input_count,
                    valid_count,
                    inserted_count,
                    duplicate_count,
                    malformed_count,
                    failed_count,
                    status,
                    error_class,
                    duration_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    source_file,
                    input_count,
                    valid_count,
                    inserted_count,
                    duplicate_count,
                    malformed_count,
                    failed_count,
                    status,
                    error_class,
                    duration_ms,
                ),
            )
            return int(cursor.lastrowid)

    def list_url_records(self) -> list[StoredURLRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    original_url,
                    canonical_url,
                    domain,
                    url_hash,
                    source_file,
                    review_status,
                    title,
                    original_label,
                    source_type,
                    raw_imported_status
                FROM url_records
                ORDER BY id
                """
            ).fetchall()

        return [
            _stored_url_record_from_row(row)
            for row in rows
        ]

    def get_url_record(self, record_id: int) -> StoredURLRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    original_url,
                    canonical_url,
                    domain,
                    url_hash,
                    source_file,
                    review_status,
                    title,
                    original_label,
                    source_type,
                    raw_imported_status
                FROM url_records
                WHERE id = ?
                """,
                (record_id,),
            ).fetchone()

        return _stored_url_record_from_row(row) if row is not None else None

    def search_url_records(
        self,
        *,
        query: str | None = None,
        domain: str | None = None,
        review_status: str | None = None,
    ) -> list[StoredURLRecord]:
        if review_status is not None:
            validate_review_status(review_status)

        conditions: list[str] = []
        parameters: list[str] = []

        if query:
            like_query = f"%{query}%"
            conditions.append(
                """
                (
                    original_url LIKE ?
                    OR canonical_url LIKE ?
                    OR domain LIKE ?
                    OR source_file LIKE ?
                    OR title LIKE ?
                    OR source_type LIKE ?
                )
                """
            )
            parameters.extend(
                [like_query, like_query, like_query, like_query, like_query, like_query]
            )

        if domain:
            conditions.append("domain = ?")
            parameters.append(domain)

        if review_status:
            conditions.append("review_status = ?")
            parameters.append(review_status)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    original_url,
                    canonical_url,
                    domain,
                    url_hash,
                    source_file,
                    review_status,
                    title,
                    original_label,
                    source_type,
                    raw_imported_status
                FROM url_records
                {where_clause}
                ORDER BY id
                """,
                parameters,
            ).fetchall()

        return [_stored_url_record_from_row(row) for row in rows]

    def update_review_status(self, record_id: int, review_status: str) -> StoredURLRecord | None:
        validate_review_status(review_status)

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE url_records
                SET review_status = ?
                WHERE id = ?
                """,
                (review_status, record_id),
            )

            if cursor.rowcount == 0:
                return None

            row = connection.execute(
                """
                SELECT
                    id,
                    original_url,
                    canonical_url,
                    domain,
                    url_hash,
                    source_file,
                    review_status,
                    title,
                    original_label,
                    source_type,
                    raw_imported_status
                FROM url_records
                WHERE id = ?
                """,
                (record_id,),
            ).fetchone()

        return _stored_url_record_from_row(row)

    def list_ingest_runs(self) -> list[StoredIngestRun]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    run_id,
                    source_file,
                    input_count,
                    valid_count,
                    inserted_count,
                    duplicate_count,
                    malformed_count,
                    failed_count,
                    status
                FROM ingest_runs
                ORDER BY id
                """
            ).fetchall()

        return [
            StoredIngestRun(
                id=row["id"],
                run_id=row["run_id"],
                source_file=row["source_file"],
                input_count=row["input_count"],
                valid_count=row["valid_count"],
                inserted_count=row["inserted_count"],
                duplicate_count=row["duplicate_count"],
                malformed_count=row["malformed_count"],
                failed_count=row["failed_count"],
                status=row["status"],
            )
            for row in rows
        ]

    def list_source_occurrences(self) -> list[StoredSourceOccurrence]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    url_record_id,
                    source_file,
                    source_format,
                    original_url,
                    original_label,
                    source_section,
                    row_number,
                    block_number,
                    raw_imported_status
                FROM source_occurrences
                ORDER BY id
                """
            ).fetchall()

        return [_stored_source_occurrence_from_row(row) for row in rows]

    def list_source_occurrences_for_record_ids(
        self, record_ids: list[int]
    ) -> dict[int, list[StoredSourceOccurrence]]:
        if not record_ids:
            return {}

        placeholders = ",".join("?" for _ in record_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    url_record_id,
                    source_file,
                    source_format,
                    original_url,
                    original_label,
                    source_section,
                    row_number,
                    block_number,
                    raw_imported_status
                FROM source_occurrences
                WHERE url_record_id IN ({placeholders})
                ORDER BY url_record_id, id
                """,
                record_ids,
            ).fetchall()

        grouped: dict[int, list[StoredSourceOccurrence]] = {}
        for row in rows:
            occurrence = _stored_source_occurrence_from_row(row)
            grouped.setdefault(occurrence.url_record_id, []).append(occurrence)

        return grouped

    def insert_ai_enrichment(
        self,
        *,
        run_id: str,
        url_record_id: int,
        provider: str,
        model: str,
        prompt_version: str,
        input_hash: str,
        status: str,
        output_json: str,
        token_input_count: int | None = None,
        token_output_count: int | None = None,
        estimated_cost_usd: float | None = None,
        error_class: str | None = None,
    ) -> int:
        validate_enrichment_review_status(status)

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ai_enrichments (
                    run_id,
                    url_record_id,
                    provider,
                    model,
                    prompt_version,
                    input_hash,
                    status,
                    output_json,
                    token_input_count,
                    token_output_count,
                    estimated_cost_usd,
                    error_class
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    url_record_id,
                    provider,
                    model,
                    prompt_version,
                    input_hash,
                    status,
                    output_json,
                    token_input_count,
                    token_output_count,
                    estimated_cost_usd,
                    error_class,
                ),
            )
            return int(cursor.lastrowid)

    def list_ai_enrichments(self) -> list[StoredAIEnrichment]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    run_id,
                    url_record_id,
                    provider,
                    model,
                    prompt_version,
                    input_hash,
                    status,
                    output_json,
                    token_input_count,
                    token_output_count,
                    estimated_cost_usd,
                    error_class,
                    created_at,
                    reviewed_at,
                    reviewer_note
                FROM ai_enrichments
                ORDER BY id
                """
            ).fetchall()

        return [_stored_ai_enrichment_from_row(row) for row in rows]

    def list_ai_enrichments_with_urls(
        self,
        *,
        status: str | None = None,
        provider: str | None = None,
        limit: int | None = None,
    ) -> list[StoredAIEnrichmentWithURL]:
        if status is not None:
            validate_enrichment_review_status(status)
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")

        conditions: list[str] = []
        parameters: list[str | int] = []

        if status:
            conditions.append("e.status = ?")
            parameters.append(status)

        if provider:
            conditions.append("e.provider = ?")
            parameters.append(provider)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    e.id AS enrichment_id,
                    e.run_id,
                    e.url_record_id,
                    e.provider,
                    e.model,
                    e.prompt_version,
                    e.input_hash,
                    e.status,
                    e.output_json,
                    e.token_input_count,
                    e.token_output_count,
                    e.estimated_cost_usd,
                    e.error_class,
                    e.created_at AS enrichment_created_at,
                    e.reviewed_at,
                    e.reviewer_note,
                    r.id AS record_id,
                    r.original_url,
                    r.canonical_url,
                    r.domain,
                    r.url_hash,
                    r.source_file,
                    r.review_status,
                    r.title,
                    r.original_label,
                    r.source_type,
                    r.raw_imported_status
                FROM ai_enrichments e
                JOIN url_records r ON r.id = e.url_record_id
                {where_clause}
                ORDER BY e.id
                {limit_clause}
                """,
                parameters,
            ).fetchall()

        return [_stored_ai_enrichment_with_url_from_row(row) for row in rows]

    def list_ai_enrichments_for_url_record_id(
        self, url_record_id: int
    ) -> list[StoredAIEnrichment]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    run_id,
                    url_record_id,
                    provider,
                    model,
                    prompt_version,
                    input_hash,
                    status,
                    output_json,
                    token_input_count,
                    token_output_count,
                    estimated_cost_usd,
                    error_class,
                    created_at,
                    reviewed_at,
                    reviewer_note
                FROM ai_enrichments
                WHERE url_record_id = ?
                ORDER BY id
                """,
                (url_record_id,),
            ).fetchall()

        return [_stored_ai_enrichment_from_row(row) for row in rows]

    def get_ai_enrichment_with_url(
        self, enrichment_id: int
    ) -> StoredAIEnrichmentWithURL | None:
        matches = self._select_ai_enrichments_with_urls_by_id(enrichment_id)
        return matches[0] if matches else None

    def update_ai_enrichment_review(
        self,
        *,
        enrichment_id: int,
        status: str,
        reviewed_at: str,
        reviewer_note: str | None = None,
    ) -> tuple[StoredAIEnrichmentWithURL, str] | None:
        validate_enrichment_review_status(status)

        with self._connect() as connection:
            previous = connection.execute(
                "SELECT status FROM ai_enrichments WHERE id = ?",
                (enrichment_id,),
            ).fetchone()
            if previous is None:
                return None

            connection.execute(
                """
                UPDATE ai_enrichments
                SET status = ?,
                    reviewed_at = ?,
                    reviewer_note = ?
                WHERE id = ?
                """,
                (status, reviewed_at, reviewer_note, enrichment_id),
            )

        updated = self.get_ai_enrichment_with_url(enrichment_id)
        if updated is None:
            return None
        return updated, str(previous["status"])

    def count_ai_enrichments(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM ai_enrichments").fetchone()[0])

    def count_ingest_runs(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0])

    def source_occurrences_by_format(self) -> dict[str, int]:
        return self._grouped_count(
            """
            SELECT source_format AS name, COUNT(*) AS count
            FROM source_occurrences
            GROUP BY source_format
            ORDER BY count DESC, name ASC
            """
        )

    def url_records_by_review_status(self) -> dict[str, int]:
        return self._grouped_count(
            """
            SELECT review_status AS name, COUNT(*) AS count
            FROM url_records
            GROUP BY review_status
            ORDER BY count DESC, name ASC
            """
        )

    def ai_enrichments_by_status(self) -> dict[str, int]:
        return self._grouped_count(
            """
            SELECT status AS name, COUNT(*) AS count
            FROM ai_enrichments
            GROUP BY status
            ORDER BY count DESC, name ASC
            """
        )

    def count_distinct_enriched_url_records(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(DISTINCT url_record_id) FROM ai_enrichments"
                ).fetchone()[0]
            )

    def ingest_failure_summary(self) -> tuple[int, int, dict[str, int]]:
        with self._connect() as connection:
            totals = connection.execute(
                """
                SELECT
                    COALESCE(SUM(failed_count), 0) AS failed_count,
                    COALESCE(SUM(malformed_count), 0) AS malformed_count
                FROM ingest_runs
                """
            ).fetchone()
            rows = connection.execute(
                """
                SELECT error_class AS name, COALESCE(SUM(failed_count), 0) AS count
                FROM ingest_runs
                WHERE error_class IS NOT NULL
                GROUP BY error_class
                ORDER BY count DESC, name ASC
                """
            ).fetchall()

        return (
            int(totals["failed_count"]),
            int(totals["malformed_count"]),
            {row["name"]: int(row["count"]) for row in rows},
        )

    def latest_ingest_runs(self, limit: int) -> list[StoredLatestIngestRun]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    source_file,
                    input_count,
                    valid_count,
                    inserted_count,
                    duplicate_count,
                    malformed_count,
                    failed_count,
                    status,
                    created_at
                FROM ingest_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            StoredLatestIngestRun(
                id=row["id"],
                source_file=row["source_file"],
                input_count=row["input_count"],
                valid_count=row["valid_count"],
                inserted_count=row["inserted_count"],
                duplicate_count=row["duplicate_count"],
                malformed_count=row["malformed_count"],
                failed_count=row["failed_count"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def top_domains(self, limit: int) -> list[tuple[str, int]]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT domain, COUNT(*) AS count
                FROM url_records
                GROUP BY domain
                ORDER BY count DESC, domain ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [(row["domain"], int(row["count"])) for row in rows]

    def count_records_with_multiple_occurrences(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT url_record_id
                        FROM source_occurrences
                        GROUP BY url_record_id
                        HAVING COUNT(*) > 1
                    )
                    """
                ).fetchone()[0]
            )

    def top_records_with_multiple_occurrences(
        self, limit: int
    ) -> list[MultiOccurrenceURLRecord]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    r.id AS url_record_id,
                    r.domain,
                    COUNT(o.id) AS occurrence_count
                FROM url_records r
                JOIN source_occurrences o ON o.url_record_id = r.id
                GROUP BY r.id, r.domain
                HAVING COUNT(o.id) > 1
                ORDER BY occurrence_count DESC, r.id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            MultiOccurrenceURLRecord(
                url_record_id=row["url_record_id"],
                domain=row["domain"],
                occurrence_count=int(row["occurrence_count"]),
            )
            for row in rows
        ]

    def count_source_occurrences(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM source_occurrences").fetchone()[0])

    def count_url_records(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM url_records").fetchone()[0])

    def _grouped_count(self, query: str) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return {row["name"]: int(row["count"]) for row in rows}

    def _connect(self) -> sqlite3.Connection:
        if self.database_path == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = sqlite3.connect(self.database_path)
                self._memory_connection.row_factory = sqlite3.Row
            return self._memory_connection

        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_url_record_columns(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(url_records)").fetchall()
        }
        column_definitions = {
            "title": "TEXT",
            "original_label": "TEXT",
            "source_type": "TEXT",
            "raw_imported_status": "TEXT",
        }

        for column_name, column_type in column_definitions.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE url_records ADD COLUMN {column_name} {column_type}"
                )

    def _ensure_ai_enrichment_columns(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(ai_enrichments)").fetchall()
        }
        column_definitions = {
            "run_id": "TEXT",
            "reviewed_at": "TEXT",
            "reviewer_note": "TEXT",
        }

        for column_name, column_type in column_definitions.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE ai_enrichments ADD COLUMN {column_name} {column_type}"
                )

    def _select_ai_enrichments_with_urls_by_id(
        self, enrichment_id: int
    ) -> list[StoredAIEnrichmentWithURL]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    e.id AS enrichment_id,
                    e.run_id,
                    e.url_record_id,
                    e.provider,
                    e.model,
                    e.prompt_version,
                    e.input_hash,
                    e.status,
                    e.output_json,
                    e.token_input_count,
                    e.token_output_count,
                    e.estimated_cost_usd,
                    e.error_class,
                    e.created_at AS enrichment_created_at,
                    e.reviewed_at,
                    e.reviewer_note,
                    r.id AS record_id,
                    r.original_url,
                    r.canonical_url,
                    r.domain,
                    r.url_hash,
                    r.source_file,
                    r.review_status,
                    r.title,
                    r.original_label,
                    r.source_type,
                    r.raw_imported_status
                FROM ai_enrichments e
                JOIN url_records r ON r.id = e.url_record_id
                WHERE e.id = ?
                ORDER BY e.id
                """,
                (enrichment_id,),
            ).fetchall()

        return [_stored_ai_enrichment_with_url_from_row(row) for row in rows]


def parse_sqlite_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    if parsed.scheme != "sqlite":
        raise ValueError("Only sqlite database URLs are supported")

    path = unquote(parsed.path)
    if path == "/:memory:":
        return ":memory:"
    if not path:
        raise ValueError("SQLite database URL must include a path")
    if path.startswith("//"):
        return path[1:]
    if path.startswith("/") and not path.startswith("//"):
        path = path[1:]

    return path


def validate_review_status(review_status: str) -> None:
    if review_status not in REVIEW_STATUSES:
        allowed = ", ".join(sorted(REVIEW_STATUSES))
        raise ValueError(f"review_status must be one of: {allowed}")


def validate_enrichment_review_status(status: str) -> None:
    if status not in ENRICHMENT_REVIEW_STATUSES:
        allowed = ", ".join(sorted(ENRICHMENT_REVIEW_STATUSES))
        raise ValueError(f"enrichment review status must be one of: {allowed}")


def _stored_url_record_from_row(row: sqlite3.Row) -> StoredURLRecord:
    return StoredURLRecord(
        id=row["id"],
        original_url=row["original_url"],
        canonical_url=row["canonical_url"],
        domain=row["domain"],
        url_hash=row["url_hash"],
        source_file=row["source_file"],
        review_status=row["review_status"],
        title=row["title"],
        original_label=row["original_label"],
        source_type=row["source_type"],
        raw_imported_status=row["raw_imported_status"],
    )


def _stored_source_occurrence_from_row(row: sqlite3.Row) -> StoredSourceOccurrence:
    return StoredSourceOccurrence(
        id=row["id"],
        url_record_id=row["url_record_id"],
        source_file=row["source_file"],
        source_format=row["source_format"],
        original_url=row["original_url"],
        original_label=row["original_label"],
        source_section=row["source_section"],
        row_number=row["row_number"],
        block_number=row["block_number"],
        raw_imported_status=row["raw_imported_status"],
    )


def _stored_ai_enrichment_from_row(row: sqlite3.Row) -> StoredAIEnrichment:
    return StoredAIEnrichment(
        id=row["id"],
        run_id=row["run_id"],
        url_record_id=row["url_record_id"],
        provider=row["provider"],
        model=row["model"],
        prompt_version=row["prompt_version"],
        input_hash=row["input_hash"],
        status=row["status"],
        output_json=row["output_json"],
        token_input_count=row["token_input_count"],
        token_output_count=row["token_output_count"],
        estimated_cost_usd=row["estimated_cost_usd"],
        error_class=row["error_class"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
        reviewer_note=row["reviewer_note"],
    )


def _stored_ai_enrichment_with_url_from_row(
    row: sqlite3.Row,
) -> StoredAIEnrichmentWithURL:
    return StoredAIEnrichmentWithURL(
        enrichment=StoredAIEnrichment(
            id=row["enrichment_id"],
            run_id=row["run_id"],
            url_record_id=row["url_record_id"],
            provider=row["provider"],
            model=row["model"],
            prompt_version=row["prompt_version"],
            input_hash=row["input_hash"],
            status=row["status"],
            output_json=row["output_json"],
            token_input_count=row["token_input_count"],
            token_output_count=row["token_output_count"],
            estimated_cost_usd=row["estimated_cost_usd"],
            error_class=row["error_class"],
            created_at=row["enrichment_created_at"],
            reviewed_at=row["reviewed_at"],
            reviewer_note=row["reviewer_note"],
        ),
        url_record=StoredURLRecord(
            id=row["record_id"],
            original_url=row["original_url"],
            canonical_url=row["canonical_url"],
            domain=row["domain"],
            url_hash=row["url_hash"],
            source_file=row["source_file"],
            review_status=row["review_status"],
            title=row["title"],
            original_label=row["original_label"],
            source_type=row["source_type"],
            raw_imported_status=row["raw_imported_status"],
        ),
    )
