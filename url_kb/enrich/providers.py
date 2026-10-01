from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Protocol

from url_kb.storage.sqlite_repo import StoredURLRecord

DEFAULT_MOCK_MODEL = "mock-local-v1"
DEFAULT_PROMPT_VERSION = "url_metadata_v1"
SUPPORTED_PROVIDERS = frozenset({"mock"})


@dataclass(frozen=True)
class EnrichmentInput:
    record_id: int
    canonical_url: str
    original_url: str
    domain: str
    title: str | None
    original_label: str | None
    source_type: str | None
    raw_imported_status: str | None
    prompt_version: str

    @classmethod
    def from_record(cls, record: StoredURLRecord, prompt_version: str) -> EnrichmentInput:
        return cls(
            record_id=record.id,
            canonical_url=record.canonical_url,
            original_url=record.original_url,
            domain=record.domain,
            title=record.title,
            original_label=record.original_label,
            source_type=record.source_type,
            raw_imported_status=record.raw_imported_status,
            prompt_version=prompt_version,
        )


@dataclass(frozen=True)
class EnrichmentOutput:
    summary: str
    topics: list[str]
    content_type: str
    confidence: float
    notes: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderResult:
    output: EnrichmentOutput
    token_input_count: int | None
    token_output_count: int | None
    estimated_cost_usd: float | None
    error_class: str | None = None


class EnrichmentProvider(Protocol):
    name: str
    default_model: str

    def enrich(self, enrichment_input: EnrichmentInput, *, model: str) -> ProviderResult:
        """Return draft metadata for a persisted URL record."""


class MockEnrichmentProvider:
    name = "mock"
    default_model = DEFAULT_MOCK_MODEL

    def enrich(self, enrichment_input: EnrichmentInput, *, model: str) -> ProviderResult:
        label = enrichment_input.title or enrichment_input.original_label
        display_name = label or enrichment_input.canonical_url
        source_type = enrichment_input.source_type or "url"
        topics = _mock_topics(enrichment_input)
        output = EnrichmentOutput(
            summary=f"Mock draft metadata for {display_name}.",
            topics=topics,
            content_type=source_type,
            confidence=0.5,
            notes=(
                "Deterministic mock enrichment only; pending human review and not based on "
                "fetched page content."
            ),
        )
        output_text = json.dumps(output.to_dict(), sort_keys=True)
        return ProviderResult(
            output=output,
            token_input_count=_wordish_count(json.dumps(asdict(enrichment_input), sort_keys=True)),
            token_output_count=_wordish_count(output_text),
            estimated_cost_usd=0.0,
        )


def get_enrichment_provider(provider_name: str) -> EnrichmentProvider:
    if provider_name == "mock":
        return MockEnrichmentProvider()

    allowed = ", ".join(sorted(SUPPORTED_PROVIDERS))
    raise ValueError(f"provider must be one of: {allowed}")


def input_hash(enrichment_input: EnrichmentInput, *, provider: str, model: str) -> str:
    payload = {
        "input": asdict(enrichment_input),
        "model": model,
        "provider": provider,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _mock_topics(enrichment_input: EnrichmentInput) -> list[str]:
    topics: list[str] = []
    for value in (
        enrichment_input.source_type,
        enrichment_input.domain,
        enrichment_input.title,
        enrichment_input.original_label,
    ):
        if not value:
            continue
        for candidate in re.findall(r"[A-Za-z0-9]+", value.lower()):
            if len(candidate) < 3 or candidate in topics:
                continue
            topics.append(candidate)
            if len(topics) == 5:
                return topics

    return topics or ["url"]


def _wordish_count(value: str) -> int:
    return len(re.findall(r"\S+", value))
