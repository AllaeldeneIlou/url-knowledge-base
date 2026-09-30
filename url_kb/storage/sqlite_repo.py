from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from url_kb.ingest.normalize import NormalizedURL


@dataclass(frozen=True)
class StoredURLRecord:
    id: int
    original_url: str
    canonical_url: str
    domain: str
    url_hash: str
    source_file: str
    review_status: str


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
                """
            )

    def insert_url_record(self, url: NormalizedURL, source_file: str) -> tuple[bool, int]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO url_records (
                    original_url,
                    canonical_url,
                    domain,
                    url_hash,
                    source_file
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    url.original_url,
                    url.canonical_url,
                    url.domain,
                    url.url_hash,
                    source_file,
                ),
            )

            if cursor.rowcount == 1:
                return True, int(cursor.lastrowid)

            existing_id = connection.execute(
                "SELECT id FROM url_records WHERE canonical_url = ? OR url_hash = ?",
                (url.canonical_url, url.url_hash),
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
                    review_status
                FROM url_records
                ORDER BY id
                """
            ).fetchall()

        return [
            StoredURLRecord(
                id=row["id"],
                original_url=row["original_url"],
                canonical_url=row["canonical_url"],
                domain=row["domain"],
                url_hash=row["url_hash"],
                source_file=row["source_file"],
                review_status=row["review_status"],
            )
            for row in rows
        ]

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
