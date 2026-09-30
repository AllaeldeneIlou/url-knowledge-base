from __future__ import annotations

from collections.abc import Iterable

from url_kb.ingest.normalize import NormalizedURL


def dedupe_normalized(urls: Iterable[NormalizedURL]) -> list[NormalizedURL]:
    """Return first-seen URLs, keyed by canonical URL."""
    seen: set[str] = set()
    unique: list[NormalizedURL] = []

    for item in urls:
        if item.canonical_url in seen:
            continue
        seen.add(item.canonical_url)
        unique.append(item)

    return unique
