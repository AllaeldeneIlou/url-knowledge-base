from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from url_kb.ingest.normalize import InvalidURLError, normalize_url
from url_kb.ingest.parser import (
    MARKDOWN_LINK_RE,
    SCHEME_URL_RE,
    TRAILING_URL_PUNCTUATION,
    ParsedURLRecord,
    ParsedURLRows,
    URLRowError,
)
from url_kb.ingest.service import IngestBatchResult, _ingest_parsed_rows
from url_kb.storage.sqlite_repo import SQLiteURLRepository

CLIPBOARD_SOURCE_FORMAT = "clipboard_markdown_links"
DEFAULT_CLIPBOARD_SOURCE_TYPE = "tab_manager_clipboard"
CLIPBOARD_RAW_IMPORTED_STATUS = "captured"
IMAGE_MARKDOWN_LINK_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")


@dataclass(frozen=True)
class ClipboardPreviewRecord:
    row_number: int
    block_number: int
    domain: str
    canonical_url: str
    original_label: str | None
    status: str


@dataclass(frozen=True)
class ClipboardParseResult:
    batch_title: str | None
    source_type: str
    source_file: str
    parsed_rows: ParsedURLRows

    @property
    def records(self) -> list[ClipboardPreviewRecord]:
        return [
            ClipboardPreviewRecord(
                row_number=record.row_number,
                block_number=record.block_number or 1,
                domain=record.normalized_url.domain,
                canonical_url=record.normalized_url.canonical_url,
                original_label=record.original_label,
                status="valid",
            )
            for record in self.parsed_rows.records
        ]

    @property
    def input_count(self) -> int:
        return len(self.parsed_rows.records) + len(self.parsed_rows.errors)

    @property
    def valid_count(self) -> int:
        return len(self.parsed_rows.records)

    @property
    def malformed_count(self) -> int:
        return len(self.parsed_rows.errors)

    @property
    def error_reason_counts(self) -> dict[str, int]:
        return dict(Counter(error.reason for error in self.parsed_rows.errors))

    def to_dict(self) -> dict[str, object]:
        return {
            "batch_title": self.batch_title,
            "source_type": self.source_type,
            "source_file": self.source_file,
            "input_count": self.input_count,
            "valid_count": self.valid_count,
            "malformed_count": self.malformed_count,
            "error_reason_counts": self.error_reason_counts,
            "records": [asdict(record) for record in self.records],
        }


def parse_clipboard_export(
    pasted_text: str,
    *,
    batch_title: str | None = None,
    source_type: str | None = None,
) -> ClipboardParseResult:
    normalized_text = _normalize_pasted_text(pasted_text)
    resolved_source_type = _clean_text(source_type) or DEFAULT_CLIPBOARD_SOURCE_TYPE
    resolved_title = _clean_text(batch_title) or _infer_batch_title(normalized_text)
    source_file = _stable_source_file(
        pasted_text=normalized_text,
        batch_title=resolved_title,
        source_type=resolved_source_type,
    )
    records: list[ParsedURLRecord] = []
    errors: list[URLRowError] = []

    for row_number, line in enumerate(normalized_text.splitlines(), start=1):
        for block_number, link in enumerate(_links_in_line(line), start=1):
            try:
                normalized_url = normalize_url(link.raw_url)
            except (InvalidURLError, ValueError) as exc:
                errors.append(
                    URLRowError(
                        row_number=row_number,
                        raw_url=link.raw_url,
                        reason=str(exc),
                    )
                )
                continue

            records.append(
                ParsedURLRecord(
                    row_number=row_number,
                    normalized_url=normalized_url,
                    original_label=_clean_text(link.label),
                    source_type=resolved_source_type,
                    raw_imported_status=CLIPBOARD_RAW_IMPORTED_STATUS,
                    source_section=resolved_title,
                    source_format=CLIPBOARD_SOURCE_FORMAT,
                    block_number=block_number,
                )
            )

    return ClipboardParseResult(
        batch_title=resolved_title,
        source_type=resolved_source_type,
        source_file=source_file,
        parsed_rows=ParsedURLRows(records=records, errors=errors),
    )


def ingest_clipboard_export(
    pasted_text: str,
    repository: SQLiteURLRepository,
    *,
    batch_title: str | None = None,
    source_type: str | None = None,
) -> tuple[ClipboardParseResult, IngestBatchResult]:
    parsed = parse_clipboard_export(
        pasted_text,
        batch_title=batch_title,
        source_type=source_type,
    )
    repository.initialize()
    ingest_result = _ingest_parsed_rows(
        Path(parsed.source_file),
        repository,
        parsed.parsed_rows,
    )
    return parsed, ingest_result


@dataclass(frozen=True)
class _LineLink:
    start: int
    raw_url: str
    label: str | None = None


def _links_in_line(line: str) -> list[_LineLink]:
    links: list[_LineLink] = []
    masked_line = line

    for match in IMAGE_MARKDOWN_LINK_RE.finditer(line):
        masked_line = _mask_span(masked_line, match.start(), match.end())

    for match in MARKDOWN_LINK_RE.finditer(line):
        raw_url = _strip_trailing_url_punctuation(match.group(2))
        links.append(_LineLink(start=match.start(), raw_url=raw_url, label=match.group(1)))
        masked_line = _mask_span(masked_line, match.start(), match.end())

    for match in SCHEME_URL_RE.finditer(masked_line):
        links.append(
            _LineLink(
                start=match.start(),
                raw_url=_strip_trailing_url_punctuation(match.group(0)),
            )
        )

    return sorted(links, key=lambda link: link.start)


def _infer_batch_title(pasted_text: str) -> str | None:
    for line in pasted_text.splitlines():
        candidate = _clean_text(line)
        if candidate is None:
            continue
        if _links_in_line(line):
            continue
        if IMAGE_MARKDOWN_LINK_RE.search(line):
            continue
        return candidate
    return None


def _stable_source_file(
    *,
    pasted_text: str,
    batch_title: str | None,
    source_type: str,
) -> str:
    normalized_title = _normalized_identity_text(batch_title or "clipboard")
    normalized_source_type = _normalized_identity_text(source_type)
    identity_payload = "\n".join(
        [
            normalized_title,
            normalized_source_type,
            pasted_text.strip(),
        ]
    )
    content_hash = sha256(identity_payload.encode("utf-8")).hexdigest()[:16]
    return f"clipboard:{_slugify(normalized_title)}:{content_hash}"


def _normalize_pasted_text(pasted_text: str) -> str:
    return pasted_text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _normalized_identity_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "clipboard")[:60].strip("-") or "clipboard"


def _strip_trailing_url_punctuation(raw_url: str) -> str:
    return raw_url.rstrip(TRAILING_URL_PUNCTUATION)


def _mask_span(value: str, start: int, end: int) -> str:
    return f"{value[:start]}{' ' * (end - start)}{value[end:]}"
