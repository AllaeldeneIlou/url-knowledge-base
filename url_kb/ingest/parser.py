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
class ParsedURLRows:
    valid: list[NormalizedURL]
    errors: list[URLRowError]


def parse_url_csv(path: Path, url_column: str = "url") -> ParsedURLRows:
    """Parse a CSV file and normalize supported URL rows without failing the batch."""
    valid: list[NormalizedURL] = []
    errors: list[URLRowError] = []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or url_column not in reader.fieldnames:
            raise ValueError(f"CSV must include a {url_column!r} column")

        for row_number, row in enumerate(reader, start=2):
            raw_url = row.get(url_column, "")
            try:
                valid.append(normalize_url(raw_url))
            except (InvalidURLError, ValueError) as exc:
                errors.append(
                    URLRowError(
                        row_number=row_number,
                        raw_url=raw_url,
                        reason=str(exc),
                    )
                )

    return ParsedURLRows(valid=valid, errors=errors)
