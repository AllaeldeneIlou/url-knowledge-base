from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from url_kb.ingest.normalize import NormalizedURL

REVIEW_STATUSES = frozenset({"pending_review", "reviewed", "rejected"})


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
                """
            )
            self._ensure_url_record_columns(connection)

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

    def count_source_occurrences(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM source_occurrences").fetchone()[0])

    def count_url_records(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM url_records").fetchone()[0])

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
