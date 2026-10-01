from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

from url_kb.enrich.providers import (
    DEFAULT_PROMPT_VERSION,
    EnrichmentInput,
    get_enrichment_provider,
    input_hash,
)
from url_kb.storage.sqlite_repo import (
    SQLiteURLRepository,
    StoredAIEnrichmentWithURL,
    StoredURLRecord,
    validate_enrichment_review_status,
)

DEFAULT_ENRICH_LIMIT = 5
# ai_enrichments.status is the human review status for draft AI metadata.
ENRICHMENT_STATUS = "pending_review"
ENRICHMENT_REVIEW_DECISIONS = frozenset({"approved", "rejected"})


class EnrichmentNotFoundError(LookupError):
    """Raised when an AI enrichment draft cannot be found."""


@dataclass(frozen=True)
class EnrichSourcesResult:
    run_id: str
    provider: str
    model: str
    prompt_version: str
    dry_run: bool
    matching_record_count: int
    selected_record_count: int
    enriched_record_count: int
    skipped_record_count: int
    enrichment_ids: list[int]
    records: list[StoredURLRecord]

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "dry_run": self.dry_run,
            "matching_record_count": self.matching_record_count,
            "selected_record_count": self.selected_record_count,
            "enriched_record_count": self.enriched_record_count,
            "skipped_record_count": self.skipped_record_count,
            "enrichment_ids": self.enrichment_ids,
            "records": [asdict(record) for record in self.records],
        }


@dataclass(frozen=True)
class ListEnrichmentsResult:
    count: int
    enrichments: list[StoredAIEnrichmentWithURL]

    def to_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "enrichments": [
                {
                    "id": item.enrichment.id,
                    "url_record_id": item.enrichment.url_record_id,
                    "canonical_url": item.url_record.canonical_url,
                    "provider": item.enrichment.provider,
                    "model": item.enrichment.model,
                    "prompt_version": item.enrichment.prompt_version,
                    "status": item.enrichment.status,
                    "created_at": item.enrichment.created_at,
                    "reviewed_at": item.enrichment.reviewed_at,
                }
                for item in self.enrichments
            ],
        }


@dataclass(frozen=True)
class ShowEnrichmentResult:
    enrichment: StoredAIEnrichmentWithURL

    def to_dict(self) -> dict[str, object]:
        return {
            "enrichment": _enrichment_detail_dict(self.enrichment),
        }


@dataclass(frozen=True)
class ReviewEnrichmentResult:
    enrichment: StoredAIEnrichmentWithURL
    previous_status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.enrichment.enrichment.id,
            "previous_status": self.previous_status,
            "new_status": self.enrichment.enrichment.status,
            "reviewer_note": self.enrichment.enrichment.reviewer_note,
            "reviewed_at": self.enrichment.enrichment.reviewed_at,
        }


def enrich_sources(
    repository: SQLiteURLRepository,
    *,
    query: str | None = None,
    domain: str | None = None,
    review_status: str | None = None,
    limit: int = DEFAULT_ENRICH_LIMIT,
    provider_name: str = "mock",
    model: str | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    dry_run: bool = False,
) -> EnrichSourcesResult:
    if limit < 1:
        raise ValueError("limit must be at least 1")

    repository.initialize()
    provider = get_enrichment_provider(provider_name)
    resolved_model = model or provider.default_model
    run_id = str(uuid4())
    matching_records = repository.search_url_records(
        query=query,
        domain=domain,
        review_status=review_status,
    )
    selected_records = matching_records[:limit]
    enrichment_ids: list[int] = []

    if not dry_run:
        for record in selected_records:
            enrichment_input = EnrichmentInput.from_record(record, prompt_version)
            provider_result = provider.enrich(enrichment_input, model=resolved_model)
            enrichment_id = repository.insert_ai_enrichment(
                run_id=run_id,
                url_record_id=record.id,
                provider=provider.name,
                model=resolved_model,
                prompt_version=prompt_version,
                input_hash=input_hash(
                    enrichment_input,
                    provider=provider.name,
                    model=resolved_model,
                ),
                status=ENRICHMENT_STATUS,
                output_json=json.dumps(
                    provider_result.output.to_dict(),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                token_input_count=provider_result.token_input_count,
                token_output_count=provider_result.token_output_count,
                estimated_cost_usd=provider_result.estimated_cost_usd,
                error_class=provider_result.error_class,
            )
            enrichment_ids.append(enrichment_id)

    return EnrichSourcesResult(
        run_id=run_id,
        provider=provider.name,
        model=resolved_model,
        prompt_version=prompt_version,
        dry_run=dry_run,
        matching_record_count=len(matching_records),
        selected_record_count=len(selected_records),
        enriched_record_count=0 if dry_run else len(enrichment_ids),
        skipped_record_count=max(len(matching_records) - len(selected_records), 0),
        enrichment_ids=enrichment_ids,
        records=selected_records,
    )


def list_enrichments(
    repository: SQLiteURLRepository,
    *,
    status: str | None = None,
    provider: str | None = None,
    limit: int | None = None,
) -> ListEnrichmentsResult:
    repository.initialize()
    enrichments = repository.list_ai_enrichments_with_urls(
        status=status,
        provider=provider,
        limit=limit,
    )
    return ListEnrichmentsResult(count=len(enrichments), enrichments=enrichments)


def show_enrichment(
    repository: SQLiteURLRepository,
    *,
    enrichment_id: int,
) -> ShowEnrichmentResult:
    repository.initialize()
    enrichment = repository.get_ai_enrichment_with_url(enrichment_id)
    if enrichment is None:
        raise EnrichmentNotFoundError(f"AI enrichment not found: {enrichment_id}")

    return ShowEnrichmentResult(enrichment=enrichment)


def review_enrichment(
    repository: SQLiteURLRepository,
    *,
    enrichment_id: int,
    status: str,
    reviewer_note: str | None = None,
    reviewed_at: datetime | None = None,
) -> ReviewEnrichmentResult:
    validate_enrichment_review_status(status)
    if status not in ENRICHMENT_REVIEW_DECISIONS:
        allowed = ", ".join(sorted(ENRICHMENT_REVIEW_DECISIONS))
        raise ValueError(f"enrichment review decision must be one of: {allowed}")

    repository.initialize()
    reviewed_timestamp = (reviewed_at or datetime.now(UTC)).isoformat(timespec="seconds")
    updated = repository.update_ai_enrichment_review(
        enrichment_id=enrichment_id,
        status=status,
        reviewed_at=reviewed_timestamp,
        reviewer_note=reviewer_note,
    )
    if updated is None:
        raise EnrichmentNotFoundError(f"AI enrichment not found: {enrichment_id}")

    enrichment, previous_status = updated
    return ReviewEnrichmentResult(enrichment=enrichment, previous_status=previous_status)


def _enrichment_detail_dict(item: StoredAIEnrichmentWithURL) -> dict[str, object]:
    enrichment = item.enrichment
    url_record = item.url_record
    return {
        "id": enrichment.id,
        "run_id": enrichment.run_id,
        "url_record_id": enrichment.url_record_id,
        "provider": enrichment.provider,
        "model": enrichment.model,
        "prompt_version": enrichment.prompt_version,
        "input_hash": enrichment.input_hash,
        "status": enrichment.status,
        "output": json.loads(enrichment.output_json),
        "token_input_count": enrichment.token_input_count,
        "token_output_count": enrichment.token_output_count,
        "estimated_cost_usd": enrichment.estimated_cost_usd,
        "error_class": enrichment.error_class,
        "created_at": enrichment.created_at,
        "reviewed_at": enrichment.reviewed_at,
        "reviewer_note": enrichment.reviewer_note,
        "url_record": asdict(url_record),
    }
