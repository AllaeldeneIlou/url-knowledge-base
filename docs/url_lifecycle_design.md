# URL Lifecycle Design Dump

**Status:** state extraction from current planning and implementation context  
**Scope:** URL lifecycle and URL-management logic as designed through Phase 1-3  
**Rule:** no new implementation decisions are retroactively invented here; gaps are marked as `GAP` or `UNDECIDED`.

## 1. URL Lifecycle As Currently Designed

### Raw Capture

Current implemented input:

- CSV files with a `url` column.
- Sample path: `samples/public_urls.csv`.

Current owner:

- `url_kb.ingest.parser.parse_url_csv`

Planned but not implemented inputs:

- `master_url_database.csv`
- `notion_second_brain_links.csv`
- OneTab exports
- loose Markdown files
- web UI manual capture

Invariants currently guaranteed:

- The parser treats each CSV row independently.
- A malformed row is collected as a row-level error.
- A malformed row does not fail the whole batch.

Failure modes currently handled:

- missing `url` column -> `ValueError`
- empty URL -> row error from `InvalidURLError`
- unsupported URL scheme -> row error
- missing/invalid host -> row error

GAP:

- Non-CSV source parsing is not implemented.
- Title, tags, timestamp, and markdown label extraction are not implemented.

### Parsing

Current owner:

- `url_kb.ingest.parser.parse_url_csv`
- `url_kb.ingest.parser.URLRowError`
- `url_kb.ingest.parser.ParsedURLRows`

Current behavior:

- Reads CSV via `csv.DictReader`.
- Extracts the configured `url_column`, defaulting to `url`.
- Calls `normalize_url` on each row.
- Returns valid normalized records plus row-level errors.

Invariants currently guaranteed:

- Valid parsed rows are already normalized into `NormalizedURL`.
- Errors preserve `row_number`, `raw_url`, and `reason`.

Failure modes:

- CSV missing required URL column -> hard `ValueError`.
- Row-level URL errors -> collected into `URLRowError`.

GAP:

- There is no parser abstraction for multiple source types yet.
- There is no metadata parser for title, tags, timestamps, topic, source type, or existing status fields.

### Normalization

Current owner:

- `url_kb.ingest.normalize.normalize_url`
- `url_kb.ingest.normalize.NormalizedURL`
- `url_kb.ingest.normalize.InvalidURLError`

Current behavior:

- Supports only `http` and `https`.
- Trims input whitespace.
- Lowercases scheme and hostname.
- Removes trailing dot from hostname.
- Rejects missing host and hosts containing spaces.
- Removes default ports: `:80` for HTTP, `:443` for HTTPS.
- Normalizes path and ensures non-empty path becomes `/`.
- Removes URL fragment.
- Sorts query parameters.
- Generates SHA-256 hash from `canonical_url`.

Current invariants:

- `canonical_url` is deterministic for supported HTTP(S) URLs.
- `domain` is lowercase normalized hostname.
- `url_hash` is stable for the canonical URL.
- Fragments are never part of the canonical URL.

Failure modes:

- empty URL -> `InvalidURLError("URL is empty")`
- unsupported scheme -> `InvalidURLError("URL must use http or https")`
- missing host -> `InvalidURLError("URL is missing a host")`
- invalid host -> `InvalidURLError("URL host is invalid")`

UNDECIDED:

- Whether to strip common tracking query parameters.
- Whether to normalize `www.`.
- Whether to normalize YouTube-specific URL variants.
- Whether to preserve original query ordering somewhere for forensic provenance.

### Canonicalization

Current owner:

- `url_kb.ingest.normalize.normalize_url`

Current canonical fields:

- `original_url`
- `canonical_url`
- `domain`
- `url_hash`

Invariants:

- `canonical_url` is the stable identity key for URL equivalence.
- `url_hash` is a stable deterministic hash of `canonical_url`.

Persistence-level invariants:

- `url_records.canonical_url` is `UNIQUE`.
- `url_records.url_hash` is `UNIQUE`.

Failure modes:

- Canonical collisions become duplicates at persistence time.
- Hash collision is theoretically possible but not expected in practice.

GAP:

- There is no separate canonicalization provenance table yet.
- There is no stored `normalized_at` or normalization version.

### Dedupe

Current owners:

- `url_kb.ingest.dedupe.dedupe_normalized`
- `url_kb.ingest.service.ingest_batch`
- `url_kb.storage.sqlite_repo.SQLiteURLRepository.insert_url_record`

Current behavior:

- In-batch dedupe occurs before persistence.
- Repository-level dedupe occurs via `INSERT OR IGNORE` against unique `canonical_url` and `url_hash`.
- Duplicate count combines in-batch duplicates and existing-record duplicates.

Invariants:

- First-seen normalized record wins inside the batch.
- SQLite prevents duplicate canonical URLs across repeated ingests and across source files.
- The database has one persisted row per canonical URL.

Failure modes:

- Duplicate in same file -> counted as duplicate.
- Duplicate already in database -> not inserted, counted as duplicate.

GAP:

- Duplicate source provenance is not preserved beyond the first persisted `source_file`.
- There is no `url_sources` table recording all source files where the same URL appeared.
- There is no `first_seen_at` / `last_seen_at` distinction.

### Persistence Schema

Current owner:

- `url_kb.storage.sqlite_repo.SQLiteURLRepository.initialize`

Current tables:

```text
url_records
ingest_runs
```

Current `url_records` fields:

- `id`
- `original_url`
- `canonical_url`
- `domain`
- `url_hash`
- `source_file`
- `review_status`
- `created_at`

Current `ingest_runs` fields:

- `id`
- `run_id`
- `source_file`
- `input_count`
- `valid_count`
- `inserted_count`
- `duplicate_count`
- `malformed_count`
- `failed_count`
- `status`
- `error_class`
- `duration_ms`
- `created_at`

Invariants:

- `canonical_url` unique.
- `url_hash` unique.
- `review_status` defaults to `pending_review`.
- Local SQLite database is ignored under `data/`.

Failure modes:

- Invalid review status is rejected by repository logic.
- Missing record for review-status update returns `None` and service raises `URLRecordNotFoundError`.

GAP:

- The schema does not yet store `title`.
- The schema does not yet store `tags`.
- The schema does not yet store `notes`.
- The schema does not yet store `source_type`.
- The schema does not yet store `first_seen_at` separately from `created_at`.
- The schema does not preserve multiple source occurrences for one canonical URL.

### Retrieval Surfaces

Current owners:

- `url_kb.search.service.search_sources`
- `url_kb.storage.sqlite_repo.SQLiteURLRepository.search_url_records`
- CLI command `search_sources`

Current retrieval filters:

- keyword query over `original_url`, `canonical_url`, `domain`, `source_file`
- exact `domain`
- exact `review_status`

Invariants:

- Search is read-only.
- Search returns structured JSON via CLI.
- Review status filter is validated.

Failure modes:

- Invalid `review_status` -> `ValueError`.
- Empty result -> valid result with count `0`.

GAP:

- Search does not include title because title is not stored.
- Search does not include tags because tags are not stored.
- Search does not include full page content.
- Search is not semantic search and does not use embeddings.

### Source Packet Output

Current owner:

- `UNDECIDED`

Planned owner from proposed module structure:

- `url_kb.packets.markdown`
- service operation `generate_source_packet`
- future CLI command `generate_source_packet`

Current status:

- Not implemented.

Intended invariants from planning:

- Preserve citations as canonical URLs.
- Mark generated packets as `draft` or `pending_review`.
- Export Markdown.
- Do not claim full page content has been verified.

GAP:

- There is no packet schema yet.
- There is no packet file naming convention yet.
- There is no source packet table yet.
- There is no selected-record strategy yet beyond using search filters.

## 2. Ingestion Of The Existing Messy Corpus

The current implementation only supports simple CSV files with a `url` column. The following source-type designs are therefore partly planned and partly `GAP`.

### `master_url_database.csv`

Known source context:

- Existing corpus has approximately 1291 records.
- Records are currently `TO_REVIEW` / `UNCLASSIFIED`.
- Earlier observed fields include URL/domain/source/status-like metadata.

Parsing intent:

- Extract URL from the best available URL column.
- Extract title if a title/name column exists.
- Extract domain if present, but treat normalized domain as canonical.
- Extract source file from ingestion path.
- Extract existing status/topic fields as raw metadata if schema supports them later.

Current implementation:

- Only CSV with `url` column is supported.

Mapping to canonical `url_record`:

- `original_url` <- raw URL field.
- `canonical_url`, `domain`, `url_hash` <- `normalize_url`.
- `source_file` <- path of `master_url_database.csv`.
- `review_status` <- `pending_review`.

GAP:

- Current schema has no `title`, `tags`, `topic`, `source_type`, or `raw_status`.
- Current parser does not accept alternate column names.
- Existing `TO_REVIEW` / `UNCLASSIFIED` cannot yet be preserved as separate fields.

Handling missing titles:

- UNDECIDED.
- Current MVP has no title field.
- Intended safe behavior: title stays empty or placeholder until user review/enrichment.

Malformed rows:

- Current behavior: row-level error, counted as malformed/failed.

Unsupported schemes:

- Current behavior: rejected unless `http` or `https`.

Duplicates across sources:

- Current behavior: dedupe by `canonical_url` / `url_hash`.
- First persisted source wins.

GAP:

- Multiple-origin provenance is not preserved.

Provenance:

- Current: `source_file`.
- GAP: no `first_seen_at` separate from `created_at`; no source occurrence table.

Initial status:

- Current: `pending_review`.
- Mapping from `TO_REVIEW` / `UNCLASSIFIED` to `pending_review` is consistent with the safety rule that nothing is considered reviewed by accident.

### `notion_second_brain_links.csv`

Parsing intent:

- Extract URL.
- Extract title/name if present.
- Extract domain if present but recompute normalized domain.
- Extract tags/status/topic if present for future metadata.

Current implementation:

- GAP: only `url` column CSV parsing exists.

Mapping:

- Same canonical URL mapping as above.
- `source_file` should preserve the CSV path.
- `review_status` should default to `pending_review`.

Missing titles:

- UNDECIDED.
- Likely order later: explicit title/name column > markdown label > enrichment > placeholder.

Duplicates across sources:

- Current dedupe catches same canonical URL.
- GAP: source occurrence from Notion CSV is lost if URL already exists.

Provenance:

- Current: only first `source_file`.
- Required future design: preserve every source occurrence if imported from both master CSV and Notion CSV.

### OneTab Exports

Parsing intent:

- OneTab exports may contain grouped title/URL lines or browser-export-style text.
- Extract URL.
- Extract title when adjacent or line-embedded.
- Extract group/date if available.

Current implementation:

- GAP: no OneTab parser.

Mapping:

- URL -> `original_url`.
- `normalize_url` -> canonical fields.
- title -> GAP until title field exists.
- group/date -> GAP until metadata/provenance schema exists.
- review status -> `pending_review`.

Failure handling:

- Bare invalid lines should become row/source errors, not crash import.
- Unsupported schemes should be skipped/reported.

Duplicates:

- Current dedupe by canonical URL once converted into normalized records.
- GAP: no way to preserve OneTab group provenance for duplicate URLs.

### Loose Markdown Files With Mixed Link Formats

Parsing intent:

- Extract markdown links like `[label](url)`.
- Extract bare HTTP(S) URLs.
- Handle links inside longer lines.
- Preserve the label as candidate title.

Current implementation:

- GAP: no Markdown parser.

Mapping:

- markdown URL -> `original_url`
- normalized output -> `canonical_url`, `domain`, `url_hash`
- markdown label -> intended future `title`
- source path -> `source_file`
- status -> `pending_review`

Missing titles:

- Markdown bare URLs have no label.
- UNDECIDED: placeholder strategy.

Malformed rows:

- Should become source-level parse errors.
- Current CSV parser pattern can be reused conceptually, but no Markdown implementation exists.

Duplicates across sources:

- Same canonical URL should collapse to one record.
- GAP: duplicate occurrence provenance not preserved.

Deterministic guarantees currently implemented:

- Every persisted record is retrievable by `domain`, `source_file`, `review_status`, `canonical_url`, and `url_hash` at repository level.

Deterministic guarantees requested but not yet implemented:

- "every record is retrievable by at least domain + title + status + hash"

GAP:

- Title is not stored, so title retrieval is not currently guaranteed.

LLM-processable metadata available without fetching pages:

- Currently available: `original_url`, `canonical_url`, `domain`, `source_file`, `review_status`, `url_hash`.
- GAP: title is not available unless added from CSV/Markdown/user input.

## 3. The Markdown Link Format As Canonical Input And Output

Target format:

```markdown
[Create Stunning Designs with Figma + AI - YouTube](https://www.youtube.com/watch?v=IU5CUcEE1r8)
```

### Parsing Markdown Links

Current status:

- GAP: Markdown parsing is not implemented.

Intended behavior:

- Parse markdown links from loose markdown dumps.
- Extract label as candidate title.
- Extract URL as raw URL.
- Also detect bare HTTP(S) URLs in the same file.

UNDECIDED:

- Exact parser strategy.
- Whether to use a regex, a Markdown parser, or a hybrid.
- How to handle nested brackets, escaped characters, reference-style links, images, and malformed markdown.

Risk:

- Arbitrary Markdown link parsing is harder than it looks.
- A simple regex may be acceptable for controlled dumps but should not be described as complete Markdown parsing.

### Mapping Canonical Records To Markdown

Current schema:

- has `canonical_url`
- has `original_url`
- has `domain`
- does not have `title`

Intended mapping:

- Markdown URL should likely use `canonical_url` for stable export.
- Markdown label should likely use:
  1. explicit stored title if available;
  2. markdown label captured at ingest if available;
  3. user-supplied title if available;
  4. fallback to domain or canonical URL.

UNDECIDED:

- Whether exported Markdown should use `canonical_url` or preserve `original_url`.
- Whether titles should include source suffix such as `- YouTube`.
- Whether the original markdown label should be immutable provenance or editable title.

### Round-Trip Behavior

Required behavior:

```text
ingest markdown -> normalize -> store -> export markdown
```

Must not silently:

- mutate titles;
- drop original labels;
- lose the original URL;
- hide that canonicalization changed the URL.

Current status:

- GAP: no title/label/original-markdown fields exist.
- Current `original_url` preserves raw URL only, not markdown label.

Needed before lock:

- Add title/original_label design.
- Decide canonical-vs-original URL export behavior.
- Decide provenance table or source occurrence model.

## 4. New-URL Capture Via The Web Interface

Current status:

- GAP: web UI has not been implemented.
- GAP: manual URL capture has not been implemented.

### Intended User Input

Possible inputs:

- bare URL;
- markdown-formatted line;
- optional title;
- optional tags;
- optional notes.

UNDECIDED:

- Exact web form fields.
- Whether tags are MVP or later.
- Whether markdown paste is accepted directly in the first web UI.

### Title Resolution

Proposed order from current discussion:

1. user-supplied title;
2. parsed markdown label;
3. extracted later by enrichment;
4. placeholder from domain or canonical URL.

Status:

- UNDECIDED.
- Current schema has no title field.

### Record Landing Zone

Intended behavior:

- New UI-added records should land in the same `url_records` table.
- Initial status should be `pending_review`.
- They should join the same review loop as imported records.

Current compatible pieces:

- `url_records` exists.
- `review_status` defaults to `pending_review`.
- `update_review_status` exists.

GAP:

- No UI service exists for direct single-record creation.

### Dedupe At Save Time

Current compatible behavior:

- `insert_url_record` dedupes by `canonical_url` / `url_hash`.

Collision behavior today:

- Existing record is not updated.
- New duplicate is not inserted.
- Existing record id is returned internally.

UNDECIDED:

- Whether a UI duplicate should:
  - reject with "already exists";
  - update provenance;
  - update `last_seen_at`;
  - add source occurrence;
  - allow user to open existing record.

Current safest behavior:

- Do not create duplicate canonical records.
- Report duplicate to the user and point to existing record.

### Markdown Serialization

Intended behavior:

- A saved record should serialize back to `[label](url)` for export/source packets.

Current status:

- GAP: no serializer exists.
- GAP: title/label field is missing.

### Live Page Fetching

Security boundary:

- Ingestion is fetch-free by default.
- No automatic crawling or page fetching in MVP.

Intended future behavior:

- Page fetching for title/content should be optional enrichment.
- It should be approval-gated and bounded.
- It should not be part of deterministic ingest.

Status:

- Page fetching is out of current MVP scope.

## 5. Open Points And Conflicts

### GAP: Title Is Central But Not Yet Modeled

The user's requested deterministic guarantee includes retrieval by title, but the current schema does not store title.

Impact:

- Markdown round-trip cannot preserve labels.
- Source packet labels will need weak fallbacks.
- LLM processing lacks a compact human-readable title without fetching.

### GAP: Multi-Source Provenance Is Not Preserved

Current schema stores one `source_file` on `url_records`.

Impact:

- If the same URL appears in master CSV, Notion CSV, OneTab, and Markdown, only the first persisted source is preserved.
- This conflicts with the requirement that the record of origin is never lost.

Likely future need:

- `url_sources` or `source_occurrences` table.

### GAP: Existing Corpus Parsers Are Not Designed Yet

Only simple CSV with a `url` column is implemented.

Missing:

- master CSV field mapping;
- Notion CSV field mapping;
- OneTab export parser;
- Markdown dump parser.

### GAP: Markdown Round-Trip Needs Explicit Data Model

Current model preserves `original_url`, not original markdown label.

Needed fields may include:

- `title`;
- `original_label`;
- `original_markdown`;
- `source_type`;
- `source_occurrence_id`.

### UNDECIDED: Status Vocabulary

Current app status:

- `pending_review`
- `reviewed`
- `rejected`

User corpus vocabulary:

- `TO_REVIEW`
- `UNCLASSIFIED`

Decision needed:

- Preserve external/imported vocabulary separately, or map all to internal statuses plus metadata.

### UNDECIDED: Canonical URL Versus Original URL In Export

Current design favors canonical URL for stable dedupe and packet citations.

But original URL may preserve user intent, tracking context, or exact source capture.

Decision needed:

- Export canonical URL always?
- Export original URL while using canonical URL for identity?
- Export both in source packet metadata?

### UNDECIDED: Title Source Priority

Proposed but not locked:

- user title > markdown label > imported title/name > enrichment > domain/canonical fallback

Need final decision.

### Scope Risk: Markdown Parsing

Markdown parsing of arbitrary dumps can grow quickly.

Safe initial scope should probably be:

- inline links `[label](url)`;
- bare HTTP(S) URLs;
- ignore reference-style links and complex Markdown until later.

### Scope Risk: Existing Corpus Ingestion

Supporting every messy file type before the MVP could derail the build.

Safe implementation path:

1. keep sample CSV MVP;
2. add canonical schema fields needed for title/provenance;
3. add one real corpus adapter at a time.

## Decisions Needed Before Locking This Logic

1. Should `title` become a required persisted field now, optional field now, or later enhancement?
2. Should duplicate URLs preserve every source occurrence via a separate `url_sources` / `source_occurrences` table?
3. For Markdown export, should the URL be `canonical_url`, `original_url`, or both?
4. What is the final internal status vocabulary: keep `pending_review/reviewed/rejected`, map `TO_REVIEW/UNCLASSIFIED`, or store imported status separately?
5. What is the first real messy source adapter after sample CSV: `master_url_database.csv`, `notion_second_brain_links.csv`, OneTab, or Markdown dumps?
6. Should first Markdown parsing support only inline `[label](url)` plus bare URLs, leaving advanced Markdown syntax out of scope?
7. Should live page fetching for titles remain fully out of MVP, with title coming only from user/imported/markdown metadata?
