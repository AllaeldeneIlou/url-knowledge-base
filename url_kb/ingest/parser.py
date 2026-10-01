from __future__ import annotations

import csv
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from url_kb.ingest.normalize import InvalidURLError, NormalizedURL, normalize_url

MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)")
SCHEME_URL_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s<>'\"`]+")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
LOGSEQ_PROPERTY_RE = re.compile(r"^\s*-?\s*([A-Za-z][A-Za-z0-9_-]*)::\s*(.+?)\s*$")
TRAILING_URL_PUNCTUATION = ".,;:!?)]}>"


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
    block_number: int | None = None


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


def parse_markdown_links(path: Path) -> ParsedURLRows:
    records: list[ParsedURLRecord] = []
    errors: list[URLRowError] = []
    current_section: str | None = None

    for line_number, line in _read_text_lines(path):
        heading = _heading_text(line)
        if heading is not None:
            current_section = heading

        for block_number, (label, raw_url) in enumerate(_markdown_links_in_line(line), start=1):
            _append_parsed_record_or_error(
                records,
                errors,
                row_number=line_number,
                block_number=block_number,
                raw_url=raw_url,
                original_label=_optional_text(label),
                source_section=current_section,
                source_format="markdown_links",
            )

    return ParsedURLRows(records=records, errors=errors)


def parse_logseq_markdown_blocks(path: Path) -> ParsedURLRows:
    records: list[ParsedURLRecord] = []
    errors: list[URLRowError] = []
    lines = list(_read_text_lines(path))
    current_section: str | None = None

    for index, (line_number, line) in enumerate(lines):
        heading = _heading_text(line)
        if heading is not None:
            current_section = heading

        for block_number, (label, raw_url) in enumerate(_markdown_links_in_line(line), start=1):
            properties = _nearby_logseq_properties(lines, index)
            _append_parsed_record_or_error(
                records,
                errors,
                row_number=line_number,
                block_number=block_number,
                raw_url=raw_url,
                original_label=_optional_text(label),
                source_type=properties.get("type"),
                raw_imported_status=properties.get("status"),
                source_section=current_section,
                source_format="logseq_markdown_blocks",
            )

    return ParsedURLRows(records=records, errors=errors)


def parse_bare_or_mixed_url_text(path: Path) -> ParsedURLRows:
    records: list[ParsedURLRecord] = []
    errors: list[URLRowError] = []
    current_section: str | None = None
    fallback_section = path.stem

    for line_number, line in _read_text_lines(path):
        heading = _heading_text(line)
        if heading is not None:
            current_section = heading

        for block_number, raw_url in enumerate(_bare_urls_in_line(line), start=1):
            _append_parsed_record_or_error(
                records,
                errors,
                row_number=line_number,
                block_number=block_number,
                raw_url=raw_url,
                source_section=current_section or fallback_section,
                source_format="bare_or_mixed_url_text",
            )

    return ParsedURLRows(records=records, errors=errors)


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


def _read_text_lines(path: Path) -> list[tuple[int, str]]:
    return list(enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1))


def _heading_text(line: str) -> str | None:
    match = HEADING_RE.match(line)
    if match is None:
        return None
    return _optional_text(match.group(1).strip("# "))


def _markdown_links_in_line(line: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for match in MARKDOWN_LINK_RE.finditer(line):
        raw_url = _strip_trailing_url_punctuation(match.group(2))
        links.append((match.group(1), raw_url))
    return links


def _bare_urls_in_line(line: str) -> list[str]:
    return [
        _strip_trailing_url_punctuation(match.group(0))
        for match in SCHEME_URL_RE.finditer(line)
    ]


def _nearby_logseq_properties(
    lines: list[tuple[int, str]],
    index: int,
) -> dict[str, str]:
    properties: dict[str, str] = {}

    for _line_number, line in reversed(lines[max(0, index - 4) : index]):
        if _heading_text(line) is not None or _markdown_links_in_line(line):
            break
        _add_logseq_property(properties, line)

    for _line_number, line in lines[index + 1 : min(len(lines), index + 5)]:
        if _heading_text(line) is not None or _markdown_links_in_line(line):
            break
        _add_logseq_property(properties, line)

    return properties


def _add_logseq_property(properties: dict[str, str], line: str) -> None:
    match = LOGSEQ_PROPERTY_RE.match(line)
    if match is None:
        return

    key = match.group(1).strip().lower()
    value = _optional_text(match.group(2))
    if value is not None and key not in properties:
        properties[key] = value


def _append_parsed_record_or_error(
    records: list[ParsedURLRecord],
    errors: list[URLRowError],
    *,
    row_number: int,
    block_number: int | None = None,
    raw_url: str,
    original_label: str | None = None,
    source_type: str | None = None,
    raw_imported_status: str | None = None,
    source_section: str | None = None,
    source_format: str,
) -> None:
    try:
        records.append(
            ParsedURLRecord(
                row_number=row_number,
                block_number=block_number,
                normalized_url=normalize_url(raw_url),
                original_label=original_label,
                source_type=source_type,
                raw_imported_status=raw_imported_status,
                source_section=source_section,
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


def _strip_trailing_url_punctuation(raw_url: str) -> str:
    return raw_url.rstrip(TRAILING_URL_PUNCTUATION)
