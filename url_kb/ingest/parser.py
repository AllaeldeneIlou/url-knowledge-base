from __future__ import annotations

import csv
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


@dataclass(frozen=True)
class ParsedURLRows:
    records: list[ParsedURLRecord]
    errors: list[URLRowError]

    @property
    def valid(self) -> list[NormalizedURL]:
        return [record.normalized_url for record in self.records]


def parse_url_csv(path: Path, url_column: str = "url") -> ParsedURLRows:
    """Parse a CSV file and normalize supported URL rows without failing the batch."""
    records: list[ParsedURLRecord] = []
    errors: list[URLRowError] = []

    with path.open(newline="", encoding="utf-8") as handle:
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
                        original_label=_optional_text(row.get("title") or row.get("Title")),
                        source_type=_optional_text(
                            row.get("source_type")
                            or row.get("Source Type")
                            or row.get("source")
                            or row.get("Source")
                        ),
                        raw_imported_status=_optional_text(
                            row.get("status") or row.get("Status")
                        ),
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


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None
