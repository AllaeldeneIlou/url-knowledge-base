# Ingestion Logic Design

**Scope:** design only. No parser implementation, schema change, ingest execution, model call, crawling, or external corpus modification.  
**Input evidence:** `docs/corpus_recon.md`, current Phase 1-3 implementation, `docs/url_lifecycle_design.md`, original MVP contract, security/permission tiers.

## Design Target

The current app has deterministic URL normalization, CSV parsing, dedupe, SQLite persistence, ingest runs, search, and review status. The real corpus requires a richer ingestion layer that separates canonical URL identity from source occurrence provenance.

Future schema direction:

```text
url_records
  canonical identity
  title
  original_label
  domain
  canonical_url
  original_url
  url_hash
  source_type
  review_status
  raw_imported_status
  timestamps

url_sources / source_occurrences
  record id
  source file
  source format
  source section
  original raw URL
  original label
  source-specific metadata
  row number / block number / section / date
```

Current Phase 1-3 schema is intentionally smaller. Missing fields are marked `GAP`.

## Variant-To-Parser Map

### 1. `csv_master_url_database`

Observed file:

- `master_url_database.csv`

Parser contract:

- Extractable fields:
  - `id`
  - `raw_url`
  - `clean_url`
  - `domain`
  - `source_file`
  - `date_added`
  - `macro_area`
  - `source_type`
  - `status`
  - empty analysis fields: `subtopic`, `technical_depth`, `strategic_relevance`, `notes`
- `url_records` mapping:
  - `original_url` <- `raw_url`
  - `canonical_url` candidate <- proposed new normalization of `raw_url`; compare with `clean_url`
  - `domain` <- normalized host; compare with `domain`
  - `raw_imported_status` <- `status`
  - `source_type` <- `source_type`
  - `timestamps` <- `date_added`
  - `title` / `original_label`: `GAP`; not present in this CSV
- `url_sources` mapping:
  - `source_file` <- actual corpus file path
  - `source_format` <- `csv_master_url_database`
  - `row_number`
  - raw metadata: historical `id`, historical `clean_url`, `macro_area`, `source_file`, `source_type`
- Row/block-level errors:
  - missing `raw_url`
  - malformed `raw_url`
  - unsupported scheme
  - missing host
  - `clean_url` present but unparsable

Design note: `clean_url` is evidence, not authority. `raw_url != clean_url` in 920 rows, and mismatch categories show host, path, query, and scheme policy differences.

### 2. `csv_url_export` / Notion-style CSV

Observed file:

- `notion_second_brain_links.csv`

Parser contract:

- Extractable fields:
  - `Name`
  - `URL`
  - `Domain`
  - `Root Domain`
  - `Site Group`
  - `URL Pattern`
  - `PARA`, `Project`, `Area`, `Resource`, `Topic`
  - `Source Type`, `Content Format`, `Content Bucket`
  - `Status`, `CODE Stage`, `Review Queue`, `Review Priority`
  - `Validation Status`, `Validation Outcome`, `Keep Decision`, `Next Action`
  - `Summary`, `Tags`, `Why It Matters`
  - `Date Added`, `Last Checked On`
  - `Source File`, `Captured From`
- `url_records` mapping:
  - `original_url` <- `URL`
  - `title` <- `Name`
  - `original_label` <- `Name`
  - `domain` <- normalized host; compare with `Domain`
  - `source_type` <- `Source Type`
  - `raw_imported_status` <- `Status`
  - `review_status` proposal: map only through explicit decision; do not blindly trust Notion workflow values
- `url_sources` mapping:
  - `source_file` <- actual corpus file path
  - `source_format` <- `csv_url_export`
  - `row_number`
  - `source_section` <- optional `Review Queue` / `Content Bucket`
  - raw metadata: PARA/project/resource/topic/review fields, validation fields, `Captured From`, `Source File`
- Row/block-level errors:
  - missing `URL`
  - malformed `URL`
  - unsupported scheme
  - URL parse succeeds but `Domain` conflicts with normalized domain; store as warning/mismatch

Design note: this export is a high-value metadata source. It should not be flattened into the current simple CSV parser.

### 3. `logseq_markdown_blocks`

Observed files:

- `not_sorted/markdown_urls/ai-automation-e-agents.md`
- `not_sorted/markdown_urls/cloud-e-architecture.md`
- `not_sorted/markdown_urls/learning-resources.md`
- `not_sorted/markdown_urls/mlops-e-pipelines.md`
- `not_sorted/markdown_urls/problem-solving-e-frameworks.md`
- `not_sorted/markdown_urls/projects-e-ventures.md`
- `not_sorted/markdown_urls/python-engineering.md`
- `not_sorted/markdown_urls/tools-e-products.md`

Parser contract:

- Extractable fields:
  - markdown label from `- [label](url)`
  - URL
  - section heading such as `Risorse validate`, `Alta priorità`, `Noise — da verificare`
  - property lines such as `type::`
  - possible metadata lines such as `descrizione::`, `area::`, `status::`, `note::`
- `url_records` mapping:
  - `original_url` <- markdown URL
  - `title` candidate <- markdown label
  - `original_label` <- markdown label
  - `source_type` candidate <- `type::`
  - `raw_imported_status` candidate <- section-derived triage or `status::`
- `url_sources` mapping:
  - `source_file` <- corpus file path
  - `source_format` <- `logseq_markdown_blocks`
  - `source_section` <- nearest heading / triage section
  - `original_raw_url`
  - `original_label`
  - source-specific metadata: `type::`, `src::` if present, all other property lines
  - block number / line number
- Row/block-level errors:
  - markdown link with invalid URL
  - property line not attached to preceding/following link block
  - duplicate URL inside same block
  - section heading exists but no ingestable URL under it

Design note: source occurrence preservation is critical because a URL may appear in multiple macroarea files and sections.

### 4. `markdown_links`

Observed files:

- `not_sorted/urls_20260715/urls_20260715_deduplicati.md`
- `not_sorted/urls_20260715/urls_20260715_macroaree.md`
- `not_sorted/urls_20260716/urls_20260716.md`
- `not_sorted/urls_20260716/urls_20260716_deduplicati.md`
- `not_sorted/urls_20260716/urls_20260716_macroaree.md`

Parser contract:

- Extractable fields:
  - markdown label
  - URL
  - nearest heading or section if present
  - date/source batch from filename
- `url_records` mapping:
  - `original_url` <- markdown URL
  - `title` candidate <- markdown label
  - `original_label` <- markdown label
  - `raw_imported_status` candidate <- section or filename marker such as `deduplicati`, `macroaree`
- `url_sources` mapping:
  - `source_file`
  - `source_format` <- `markdown_links`
  - `source_section`
  - `original_raw_url`
  - `original_label`
  - line number
- Row/block-level errors:
  - empty label; none observed in recon, but parser should support error class
  - malformed URL
  - unsupported scheme
  - repeated URL within same file

### 5. `bare_or_mixed_url_text`

Observed files:

- 20260422 text batches
- `not_sorted/urls_20260319.txt`
- `not_sorted/urls_20260330.txt`
- `not_sorted/urls_20260715/urls_20260715.md`

Parser contract:

- Extractable fields:
  - bare URL
  - weak line context
  - possible title if the line follows a consistent `label,url` or `domain - title,url` pattern
  - source type/date from filename and parent directory
- `url_records` mapping:
  - `original_url` <- detected URL
  - `title` candidate <- parsed label when present; otherwise fallback to domain or URL path
  - `source_type` candidate <- filename category, e.g. `AI-Agents`, `ITS-AWS`
  - `raw_imported_status` <- `TO_REVIEW` by default unless section says otherwise
- `url_sources` mapping:
  - `source_file`
  - `source_format` <- `bare_or_mixed_url_text`
  - `source_section` if headings are found
  - line number
  - raw line fingerprint / redacted snippet, not full sensitive content
- Row/block-level errors:
  - URL-like string fails parsing
  - unsupported scheme
  - multiple URLs on one line where no deterministic split policy exists
  - binary/control characters in line

### 6. `index_or_macroarea_file`

Observed file:

- `not_sorted/markdown_urls/indice_macroaree.md`

Parser contract:

- Default role: **do not ingest as URL source**.
- Extractable fields:
  - index entries pointing to sibling macroarea markdown files
  - macroarea names
- Mapping:
  - no `url_records`
  - optional future import planning metadata only
- Row/block-level errors:
  - none for URL ingestion; treat URL-like content as suspicious unless verified manually

### 7. `script_or_tooling`, `appledouble_resource_fork`, `binary_or_compiled_undecided`, `undecided_text`

Parser contract:

- Default role: **exclude from ingestion**.
- If future implementation supports ODT extraction, `not_sorted/urls_20260126.odt` can be reclassified after an explicit parser decision.
- `.py`, `.pyc`, `__pycache__`, `._*`, and setup docs must not be treated as URL source files.

## Normalization Policy Proposals

These are proposals only. Do not change `normalize_url` until locked.

### YouTube URLs

Observed YouTube domains are prominent: `www.youtube.com` and `youtube.com` together account for many instances.

Proposal:

- `watch?v=`:
  - identity should preserve `v`.
  - preserve `list` when the URL is playlist-contextual and the product needs playlist identity.
  - drop `t`, `si`, `feature`, and common tracking params from identity.
- `youtu.be/<id>`:
  - normalize to the same canonical identity as `youtube.com/watch?v=<id>` or preserve as original occurrence while canonical identity maps to `watch?v=`.
  - decision required.
- Playlist URLs:
  - preserve `list`.
  - if both `v` and `list` exist, decide whether identity is video-in-playlist or video-only.
- Channel/user URLs:
  - preserve path identity.
  - drop tracking/query params unless semantically required.

### Tracking Parameter Stripping

Candidate params seen in corpus:

- `utm_*`
- `fbclid`
- `igsh`
- `si`
- `feature`
- `vjk`
- `advn`
- `authuser`
- sensitive-looking key families such as `token`, `auth`, `session`, `key`
- ambiguous fields such as `id`, `keyword`, `keywords`

Proposal:

- Strip known analytics/tracking params from canonical identity.
- Preserve sensitive-looking params only in redacted occurrence metadata if needed for debugging; never print raw values.
- Treat ambiguous business params (`id`, `keyword`, `keywords`) as `UNDECIDED` until domain-specific policy is locked.

Comparison with old `clean_url`:

- `raw_url != clean_url`: 920 rows in master CSV.
- Candidate mismatch categories:
  - host / `www.` policy: 776
  - path / trailing slash policy: 275
  - query policy: 127
  - scheme policy: 3

These categories should become explicit normalization tests before real corpus ingestion.

### `www.` Normalization

Proposal:

- Do not globally strip `www.` yet.
- Evaluate domain families:
  - `youtube.com` vs `www.youtube.com`
  - `google.com` vs `www.google.com`
  - `linkedin.com` vs `www.linkedin.com`
  - `instagram.com` vs `www.instagram.com`
- Lock a per-domain or general rule only after mismatch sampling.

### Trailing Slash Policy

Current implementation ensures empty path becomes `/`.

Proposal:

- Preserve `/` for host-root canonical URLs.
- Normalize empty path and `/` as equivalent.
- Preserve non-root trailing slash only if the site path semantics may differ, or decide globally after sampling old `clean_url` mismatches.

### Percent-Encoding Policy

Proposal:

- Keep canonical URL percent-encoded deterministically.
- Decode labels/titles for display only.
- Preserve raw URL in `source_occurrences` so canonicalization is reversible for audit.

### Title / Label Decoding

Observed labels and URLs may contain encoded text such as `Cloud%20DevOps%20Engineer`.

Proposal:

- Decode markdown labels and CSV titles for display.
- Never decode canonical URL path destructively unless normalization tests prove equivalence.
- Store both `original_label` and cleaned display `title` when available.

## Dedupe And Precedence Plan

Proposal, awaiting user lock:

1. Identity dedupe by canonical URL/hash.
2. First-seen wins canonical identity fields.
3. Every occurrence appends provenance to `url_sources`.
4. Best-quality title may update display title only under controlled rules:
   - prefer non-empty human-readable label over bare URL;
   - prefer Notion `Name` over filename-derived fallback;
   - never overwrite a reviewed human title automatically;
   - record title provenance.
5. Preserve all raw source statuses as `raw_imported_status`; map to internal `review_status` only through explicit rules.
6. No duplicate canonical records unless a domain-specific canonicalization exception is approved.
7. Source occurrence duplication policy is `UNDECIDED`:
   - option A: one occurrence per `(record_id, source_file, line_or_row_number)`;
   - option B: one occurrence per `(record_id, source_file, source_section, original_raw_url)`;
   - option C: preserve every import occurrence with ingest run id.

## Enrichment-Readiness Guarantee

Without fetching live pages, every successfully ingested canonical record should have:

- canonical URL
- original URL
- domain
- stable hash
- title or fallback title
- source type or source format
- source occurrence count
- source file provenance
- raw imported status, if present
- review status
- section-derived triage, if present
- import timestamp / ingest run id

Testable invariants:

- No canonical URL record exists without at least one source occurrence.
- Every source occurrence points to exactly one canonical URL record.
- Every generated source packet can cite source file provenance without live page fetch.
- Every AI enrichment candidate can be bounded by stored metadata only.
- Every sensitive query value is redacted in logs and row-level error reports.

## Malformed-Row Strategy

General rule: bad rows/blocks are row-level or block-level failures, not batch-fatal, unless the file itself cannot be opened or lacks the required source structure.

Suggested `error_class` values:

- `missing_url`
- `malformed_url`
- `unsupported_scheme`
- `missing_host`
- `invalid_csv_header`
- `malformed_csv_row`
- `malformed_markdown_link`
- `orphan_property_line`
- `multiple_urls_ambiguous_line`
- `unsupported_source_file`
- `encoding_error`
- `binary_or_compiled_file`
- `index_file_skipped`
- `normalization_mismatch_warning`

Variant-specific handling:

| Variant | Non-fatal errors | Batch-fatal errors |
|---|---|---|
| `csv_master_url_database` | malformed row URL, clean/raw mismatch warning, missing optional fields | missing required URL column(s), unreadable CSV |
| `csv_url_export` | malformed `URL`, domain mismatch warning, missing optional metadata | missing `URL` field, unreadable CSV |
| `logseq_markdown_blocks` | malformed link URL, orphan property line, unsupported scheme | unreadable file |
| `markdown_links` | malformed link, empty label, duplicate URL in file | unreadable file |
| `bare_or_mixed_url_text` | malformed line, ambiguous multi-URL line, unsupported scheme | unreadable file |
| `index_or_macroarea_file` | skipped as non-source | none unless explicitly selected as source |
| AppleDouble / bytecode / tooling | skipped as non-source | none unless explicitly selected as source |

Debug preservation:

- Preserve row number or block number.
- Preserve source file and source format.
- Preserve hashed/redacted raw snippet, not full sensitive content.
- Redact query values for sensitive keys and known tracking params.

Mapping to `ingest_runs.malformed_count`:

- Count URL-bearing row/block failures as `malformed_count`.
- Count skipped non-source files separately in a future `skipped_count` or file-level report. `GAP`: current `ingest_runs` has no `skipped_count`.
- Count normalization mismatch warnings separately from malformed rows. `GAP`: current `ingest_runs` has only one `error_class`.

## Idempotency Proof

Re-ingesting the same file twice should behave as follows:

- No new canonical duplicate records.
- Existing canonical records are matched by canonical URL/hash.
- New ingest run is logged.
- Malformed counts are deterministic for the same file and parser version.
- Title/status update rules are deterministic and provenance-aware.
- Source occurrence duplication behavior must be decided before implementation:
  - if occurrences are run-scoped, re-ingest appends new run occurrences;
  - if occurrences are source-position-scoped, re-ingest does not duplicate the same source row/block;
  - recommended default: source-position-scoped occurrence uniqueness plus ingest-run audit.

Current Phase 1-3 already proves canonical record idempotency for simple CSV ingestion. It does not preserve duplicate provenance yet.

## Conflict List

### Versus Current Phase 1-3 Implementation

- Current parser only supports CSV with a `url` column. Corpus requires master CSV, Notion CSV, markdown links, Logseq blocks, and bare/mixed URL text. `GAP`
- Current `url_records` lacks `title`, `original_label`, `source_type`, `raw_imported_status`, `first_seen_at`, and normalization version. `GAP`
- Current persistence stores one `source_file` on `url_records`; corpus needs `url_sources` / `source_occurrences`. `GAP`
- Current dedupe drops duplicate occurrence provenance. Corpus overlap makes provenance preservation necessary. `GAP`
- Current normalization sorts queries but does not strip tracking params, normalize YouTube variants, or decide `www.` policy. `UNDECIDED`
- Current `ingest_runs` has aggregate counts but no per-row error table or skipped-file count. `GAP`
- Current search is over URL/domain/source fields only; no title/status/source metadata search yet. `GAP`

### Versus `docs/url_lifecycle_design.md`

- The lifecycle design already marks non-CSV parsing, metadata parsing, provenance table, and tracking/YouTube normalization as gaps or undecided. Recon confirms those gaps.
- The lifecycle design says duplicate source provenance is not preserved; recon shows 1667 candidate URLs appear in more than one file, making this a real implementation blocker for full corpus ingestion.
- The lifecycle design treats `review_status` as internal. Recon confirms external statuses should remain `raw_imported_status` unless mapped deliberately.
- The lifecycle design does not yet distinguish skipped non-source files from malformed URL rows. Recon shows many non-source files, so the design should add skipped-file accounting.

### Versus Original MVP Contract

- MVP intentionally used sample/public data only; this recon is authorized read-only external analysis, not ingestion.
- MVP avoided uncontrolled crawling and real model calls; this design keeps enrichment metadata local and no-fetch.
- MVP source packets depend on citations; recon shows citations must include occurrence provenance, not only canonical URL rows.
- MVP had no deletion feature; this design does not add deletion.
- MVP excluded RAG/vector/MCP/framework scope; this design only creates future-ready metadata contracts.

### Versus Security And Command/Permission Tiers

- External corpus access was Tier 4 and explicitly authorized read-only for this task.
- No external corpus files should be modified, moved, renamed, deleted, normalized, or copied.
- Future real corpus ingestion remains review-gated or explicit-approval work.
- Sensitive query params must be redacted in examples, logs, row errors, and docs.
- Parser implementation, schema changes, dependency additions, migrations, commits, crawling, model/API calls, and external network calls require later approval according to the command tiers.

## Decisions To Lock Before Implementation

1. Which source variants are in the first real-corpus parser slice: master CSV only, Notion CSV, markdown links, Logseq blocks, bare URL text, or some subset?
2. Should a `url_sources` / `source_occurrences` table be added before any real corpus ingestion?
3. What is the source occurrence uniqueness policy: source-position-scoped, run-scoped, or preserve every occurrence?
4. What is the canonical identity policy for YouTube `watch?v=`, `youtu.be`, playlist URLs, and channel/user URLs?
5. Which query params are stripped from canonical identity, preserved, or redacted-only?
6. Should `www.` be normalized globally, per-domain, or not yet?
7. What are the exact rules for title precedence and whether imported titles can update existing canonical records?
8. How should external statuses map to internal `review_status` versus `raw_imported_status`?
9. Should non-source files be reported in `ingest_runs`, a separate file-level import report, or docs only?
10. What redacted row-error retention policy is acceptable for debugging without exposing sensitive raw URLs?
