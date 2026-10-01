from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from url_kb.ingest.normalize import InvalidURLError, NormalizedURL, normalize_url


@dataclass(frozen=True)
class URLRowError:
    row_number: int
    raw_url: str
    reason: str


@dataclass(frozen=True)
class ParsedURLRecord:
    row_number: int
    normalized_url: NormalizedURL
    original_label: str | None = None
    source_type: str | None = None
    raw_imported_status: str | None = None
    source_section: str | None = None
    source_format: str = "csv_url_column"


@dataclass(frozen=True)
class ParsedURLRows:
    records: list[ParsedURLRecord]
    errors: list[URLRowError]

    @property
    def valid(self) -> list[NormalizedURL]:
        return [record.normalized_url for record in self.records]


def parse_url_csv(
    path: Path,
    url_column: str = "url",
    *,
    source_format: str = "csv_url_column",
    title_columns: Sequence[str] = ("title", "Title"),
    source_type_columns: Sequence[str] = (
        "source_type",
        "Source Type",
        "source",
        "Source",
    ),
    status_columns: Sequence[str] = ("status", "Status"),
    source_section_columns: Sequence[str] = (),
) -> ParsedURLRows:
    """Parse a CSV file and normalize supported URL rows without failing the batch."""
    records: list[ParsedURLRecord] = []
    errors: list[URLRowError] = []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or url_column not in reader.fieldnames:
            raise ValueError(f"CSV must include a {url_column!r} column")

        for row_number, row in enumerate(reader, start=2):
            raw_url = row.get(url_column, "")
            try:
                records.append(
                    ParsedURLRecord(
                        row_number=row_number,
                        normalized_url=normalize_url(raw_url),
                        original_label=_first_optional_text(row, title_columns),
                        source_type=_first_optional_text(row, source_type_columns),
                        raw_imported_status=_first_optional_text(row, status_columns),
                        source_section=_first_optional_text(row, source_section_columns),
                        source_format=source_format,
                    )
                )
            except (InvalidURLError, ValueError) as exc:
                errors.append(
                    URLRowError(
                        row_number=row_number,
                        raw_url=raw_url,
                        reason=str(exc),
                    )
                )

    return ParsedURLRows(records=records, errors=errors)


def parse_master_url_database_csv(path: Path) -> ParsedURLRows:
    return parse_url_csv(
        path,
        url_column="raw_url",
        source_format="csv_master_url_database",
        title_columns=(),
        source_type_columns=("source_type",),
        status_columns=("status",),
        source_section_columns=("macro_area",),
    )


def parse_notion_url_export_csv(path: Path) -> ParsedURLRows:
    return parse_url_csv(
        path,
        url_column="URL",
        source_format="csv_url_export",
        title_columns=("Name",),
        source_type_columns=("Source Type",),
        status_columns=("Status",),
        source_section_columns=("Review Queue", "Content Bucket", "Topic", "Project"),
    )


def _first_optional_text(row: dict[str, str], columns: Sequence[str]) -> str | None:
    for column in columns:
        value = _optional_text(row.get(column))
        if value is not None:
            return value
    return None


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None
