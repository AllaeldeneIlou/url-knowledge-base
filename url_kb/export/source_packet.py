from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from url_kb.search.service import search_sources
from url_kb.storage.sqlite_repo import (
    SQLiteURLRepository,
    StoredSourceOccurrence,
    StoredURLRecord,
)


@dataclass(frozen=True)
class SourcePacketExportResult:
    output_path: Path
    record_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "output_path": str(self.output_path),
            "record_count": self.record_count,
        }


def export_source_packet(
    repository: SQLiteURLRepository,
    *,
    query: str | None = None,
    domain: str | None = None,
    review_status: str | None = None,
    output_path: Path | None = None,
    generated_at: datetime | None = None,
) -> SourcePacketExportResult:
    repository.initialize()
    generated_at = generated_at or datetime.now(UTC)
    output_path = output_path or default_source_packet_path(generated_at)

    search_result = search_sources(
        repository,
        query=query,
        domain=domain,
        review_status=review_status,
    )
    occurrences_by_record_id = repository.list_source_occurrences_for_record_ids(
        [record.id for record in search_result.records]
    )
    markdown = render_source_packet(
        records=search_result.records,
        occurrences_by_record_id=occurrences_by_record_id,
        generated_at=generated_at,
        query=query,
        domain=domain,
        review_status=review_status,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    return SourcePacketExportResult(
        output_path=output_path,
        record_count=search_result.count,
    )


def default_source_packet_path(generated_at: datetime) -> Path:
    timestamp = generated_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("outputs") / "source_packets" / f"{timestamp}_source_packet.md"


def render_source_packet(
    *,
    records: list[StoredURLRecord],
    occurrences_by_record_id: dict[int, list[StoredSourceOccurrence]],
    generated_at: datetime,
    query: str | None,
    domain: str | None,
    review_status: str | None,
) -> str:
    lines = [
        "# URL Knowledge Base Source Packet",
        "",
        "Status: draft / pending human review",
        f"Generated at: {generated_at.astimezone(UTC).isoformat()}",
        (
            f"Filters: query={_display(query)}; domain={_display(domain)}; "
            f"review_status={_display(review_status)}"
        ),
        f"Record count: {len(records)}",
        "",
        "## Sources",
        "",
    ]

    if not records:
        lines.extend(["No persisted URL records matched the selected filters.", ""])
        return "\n".join(lines)

    for index, record in enumerate(records, start=1):
        title = record.title or record.original_label or record.canonical_url
        lines.extend(
            [
                f"### {index}. {title}",
                "",
                f"- Canonical URL: {record.canonical_url}",
                f"- Original URL: {record.original_url}",
                f"- Domain: {record.domain}",
                f"- Review status: {record.review_status}",
                f"- Title: {_display(record.title)}",
                f"- Original label: {_display(record.original_label)}",
                f"- Source type: {_display(record.source_type)}",
                f"- Raw imported status: {_display(record.raw_imported_status)}",
                "",
                "Provenance:",
            ]
        )

        occurrences = occurrences_by_record_id.get(record.id, [])
        if not occurrences:
            lines.append("- No source occurrence metadata available.")
        else:
            for occurrence in occurrences:
                lines.extend(
                    [
                        f"- Source file: {occurrence.source_file}",
                        f"  - Format: {occurrence.source_format}",
                        f"  - Row: {_display_number(occurrence.row_number)}",
                        f"  - Block: {_display_number(occurrence.block_number)}",
                        f"  - Source section: {_display(occurrence.source_section)}",
                        f"  - Original URL: {occurrence.original_url}",
                        f"  - Original label: {_display(occurrence.original_label)}",
                        f"  - Raw imported status: {_display(occurrence.raw_imported_status)}",
                    ]
                )

        lines.append("")

    return "\n".join(lines)


def _display(value: str | None) -> str:
    if value is None or value == "":
        return "N/A"
    return value


def _display_number(value: int | None) -> str:
    if value is None:
        return "N/A"
    return str(value)
