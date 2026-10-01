from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from uuid import uuid4

from url_kb.enrich.providers import (
    DEFAULT_PROMPT_VERSION,
    EnrichmentInput,
    get_enrichment_provider,
    input_hash,
)
from url_kb.storage.sqlite_repo import SQLiteURLRepository, StoredURLRecord

DEFAULT_ENRICH_LIMIT = 5
ENRICHMENT_STATUS = "pending_review"


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
