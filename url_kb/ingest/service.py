from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from url_kb.ingest.dedupe import dedupe_normalized
from url_kb.ingest.parser import (
    ParsedURLRows,
    URLRowError,
    parse_bare_or_mixed_url_text,
    parse_logseq_markdown_blocks,
    parse_markdown_links,
    parse_master_url_database_csv,
    parse_notion_url_export_csv,
    parse_url_csv,
)
from url_kb.storage.sqlite_repo import SQLiteURLRepository, URLRecordOccurrenceInput

ParserFunction = Callable[[Path], ParsedURLRows]


@dataclass(frozen=True)
class PrivateCorpusProfile:
    source_paths: tuple[str, ...]
    parser: ParserFunction
    required: bool = False


PRIVATE_CORPUS_PROFILES = {
    "master_csv": PrivateCorpusProfile(
        source_paths=("master_url_database.csv",),
        parser=parse_master_url_database_csv,
        required=True,
    ),
    "notion_csv": PrivateCorpusProfile(
        source_paths=("notion_second_brain_links.csv",),
        parser=parse_notion_url_export_csv,
        required=True,
    ),
    "markdown_links": PrivateCorpusProfile(
        source_paths=(
            "not_sorted/urls_20260715/urls_20260715_deduplicati.md",
            "not_sorted/urls_20260715/urls_20260715_macroaree.md",
            "not_sorted/urls_20260716/urls_20260716.md",
            "not_sorted/urls_20260716/urls_20260716_deduplicati.md",
            "not_sorted/urls_20260716/urls_20260716_macroaree.md",
        ),
        parser=parse_markdown_links,
    ),
    "logseq_markdown_blocks": PrivateCorpusProfile(
        source_paths=(
            "not_sorted/markdown_urls/ai-automation-e-agents.md",
            "not_sorted/markdown_urls/cloud-e-architecture.md",
            "not_sorted/markdown_urls/learning-resources.md",
            "not_sorted/markdown_urls/mlops-e-pipelines.md",
            "not_sorted/markdown_urls/problem-solving-e-frameworks.md",
            "not_sorted/markdown_urls/projects-e-ventures.md",
            "not_sorted/markdown_urls/python-engineering.md",
            "not_sorted/markdown_urls/tools-e-products.md",
        ),
        parser=parse_logseq_markdown_blocks,
    ),
    "bare_or_mixed_url_text": PrivateCorpusProfile(
        source_paths=(
            "not_sorted/20260422_urls/urls_AI-Agents.txt",
            "not_sorted/20260422_urls/urls_ITS-AWS.txt",
            "not_sorted/20260422_urls/urls_Laptop.txt",
            "not_sorted/20260422_urls/urls_Persona-professional-narration.txt",
            "not_sorted/20260422_urls/urls_finanza-personale.txt",
            "not_sorted/20260422_urls/urls_inbox.txt",
            "not_sorted/20260422_urls/urls_learn.txt",
            "not_sorted/20260422_urls/urls_modulo.txt",
            "not_sorted/20260422_urls/urls_psilo.txt",
            "not_sorted/20260422_urls/urls_unitelma.txt",
            "not_sorted/20260422_urls/urls_virtual-studios.txt",
            "not_sorted/urls_20260319.txt",
            "not_sorted/urls_20260330.txt",
            "not_sorted/urls_20260715/urls_20260715.md",
        ),
        parser=parse_bare_or_mixed_url_text,
    ),
}


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


@dataclass(frozen=True)
class PrivateCorpusFileSummary:
    profile: str
    source_file: str
    input_count: int
    valid_count: int
    inserted_count: int
    duplicate_count: int
    malformed_count: int
    failed_count: int
    status: str
    error_reasons: dict[str, int]


@dataclass(frozen=True)
class PrivateCorpusIngestResult:
    corpus_path: str
    database_path: str
    files: list[PrivateCorpusFileSummary]

    @property
    def input_count(self) -> int:
        return sum(item.input_count for item in self.files)

    @property
    def valid_count(self) -> int:
        return sum(item.valid_count for item in self.files)

    @property
    def inserted_count(self) -> int:
        return sum(item.inserted_count for item in self.files)

    @property
    def duplicate_count(self) -> int:
        return sum(item.duplicate_count for item in self.files)

    @property
    def failed_count(self) -> int:
        return sum(item.failed_count for item in self.files)

    def to_dict(self) -> dict[str, object]:
        return {
            "corpus_path": self.corpus_path,
            "database_path": self.database_path,
            "input_count": self.input_count,
            "valid_count": self.valid_count,
            "inserted_count": self.inserted_count,
            "duplicate_count": self.duplicate_count,
            "failed_count": self.failed_count,
            "files": [asdict(item) for item in self.files],
        }


def ingest_batch(csv_path: Path, repository: SQLiteURLRepository) -> IngestBatchResult:
    repository.initialize()
    parsed = parse_url_csv(csv_path)
    return _ingest_parsed_rows(csv_path, repository, parsed)


def ingest_private_corpus_csvs(
    corpus_path: Path,
    repository: SQLiteURLRepository,
    *,
    profiles: list[str] | None = None,
) -> PrivateCorpusIngestResult:
    repository.initialize()
    selected_profiles = profiles or list(PRIVATE_CORPUS_PROFILES)
    summaries: list[PrivateCorpusFileSummary] = []

    for profile in selected_profiles:
        try:
            profile_config = PRIVATE_CORPUS_PROFILES[profile]
        except KeyError as exc:
            allowed = ", ".join(sorted(PRIVATE_CORPUS_PROFILES))
            raise ValueError(f"profile must be one of: {allowed}") from exc

        source_paths = [
            corpus_path / relative_path
            for relative_path in profile_config.source_paths
            if _is_ingestable_private_path(corpus_path / relative_path)
        ]
        if not source_paths and (profiles is not None or profile_config.required):
            raise FileNotFoundError(f"Private corpus profile has no source files: {profile}")

        for source_path in source_paths:
            parsed = profile_config.parser(source_path)
            result = _ingest_parsed_rows(source_path, repository, parsed)
            summaries.append(
                PrivateCorpusFileSummary(
                    profile=profile,
                    source_file=str(source_path),
                    input_count=result.input_count,
                    valid_count=result.valid_count,
                    inserted_count=result.inserted_count,
                    duplicate_count=result.duplicate_count,
                    malformed_count=result.malformed_count,
                    failed_count=result.failed_count,
                    status=result.status,
                    error_reasons=_count_error_reasons(result.errors),
                )
            )

    return PrivateCorpusIngestResult(
        corpus_path=str(corpus_path),
        database_path=repository.database_path,
        files=summaries,
    )


def _ingest_parsed_rows(
    csv_path: Path,
    repository: SQLiteURLRepository,
    parsed: ParsedURLRows,
) -> IngestBatchResult:
    source_file = str(csv_path)
    run_id = str(uuid4())
    started_at = perf_counter()

    unique_urls = dedupe_normalized(parsed.valid)
    batch_duplicate_count = len(parsed.records) - len(unique_urls)
    existing_duplicate_count = 0
    seen_batch_canonical_urls: set[str] = set()
    entries: list[URLRecordOccurrenceInput] = []
    is_batch_duplicate_by_index: list[bool] = []

    for record in parsed.records:
        url = record.normalized_url
        is_batch_duplicate = url.canonical_url in seen_batch_canonical_urls
        if not is_batch_duplicate:
            seen_batch_canonical_urls.add(url.canonical_url)
        is_batch_duplicate_by_index.append(is_batch_duplicate)

        entries.append(
            URLRecordOccurrenceInput(
                url=url,
                source_file=source_file,
                source_format=record.source_format,
                title=record.original_label,
                original_label=record.original_label,
                source_type=record.source_type,
                raw_imported_status=record.raw_imported_status,
                source_section=record.source_section,
                row_number=record.row_number,
                block_number=record.block_number,
            )
        )

    insert_results = repository.insert_url_records_with_occurrences(entries)
    inserted_count = sum(1 for result in insert_results if result.inserted)
    for insert_result, is_batch_duplicate in zip(
        insert_results, is_batch_duplicate_by_index, strict=True
    ):
        if not insert_result.inserted and not is_batch_duplicate:
            existing_duplicate_count += 1

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
        inserted_count=inserted_count,
        duplicate_count=duplicate_count,
        malformed_count=malformed_count,
        failed_count=failed_count,
        status=status,
        duration_ms=duration_ms,
        valid_count=len(parsed.valid),
        input_count=len(parsed.valid) + malformed_count,
        errors=parsed.errors,
    )


def _count_error_reasons(errors: list[URLRowError]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for error in errors:
        counts[error.reason] = counts.get(error.reason, 0) + 1
    return counts


def _is_ingestable_private_path(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if any(part.startswith("._") for part in path.parts):
        return False
    if "__pycache__" in path.parts:
        return False
    return path.suffix != ".pyc"
