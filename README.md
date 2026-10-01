# URL Knowledge Base

![CI status](https://github.com/AllaeldeneIlou/url-knowledge-base/actions/workflows/ci.yml/badge.svg)

Local-first tool for turning browser tab dumps and URL collections into a searchable,
reviewable knowledge base.

Copyright (c) Allaeldene Ilou.

## Why This Exists

The problem is not saving links. The problem is that useful sources collected during
research become passive: they sit in tabs, OneTab groups, CSV exports, notes, and
Markdown files, but they are hard to retrieve when work actually starts.

This project was built around that real workflow pain:

```text
valuable source found while browsing
  -> saved somewhere
  -> loses context
  -> stays unreviewed
  -> cannot be reused during writing, learning, or technical preparation
```

URL Knowledge Base converts that messy capture layer into structured operational
knowledge: normalized URLs, provenance, search, review status, enrichment drafts,
metrics, and task-specific source packets.

## Product Slice

The current system supports a complete local workflow:

| Area | Implemented |
|---|---|
| Capture | Paste OneTab or Markdown-style link batches through the web UI |
| Ingestion | Import public samples and private local corpus formats |
| Normalization | Canonical URL handling, domain extraction, deduplication |
| Provenance | Source file, row, section, line, batch, source format, source type |
| Search | Filter by query, domain, and review status |
| Review | Inspect individual records and enrichment drafts |
| AI boundary | Mock enrichment provider with provider/model/run metadata |
| Export | Markdown source packets for task-specific research context |
| Metrics | Counts, dedupe rate, failures, source formats, enrichment coverage |
| Delivery | Dockerfile, Docker Compose, GitHub Actions CI, web smoke tests |

## What This Proves

This is the signal I want the project to show in a technical interview:

- I can turn a messy personal workflow into a bounded software system.
- I separate deterministic automation from AI-assisted interpretation.
- I design for traceability, review, privacy, and failure states before scaling.
- I use tests, Docker, and CI/CD as delivery controls, not as decoration.
- I can explain the production path without pretending the MVP is already an
  enterprise platform.

## Why This Is Not A Full Agent Demo

I did not start by wrapping the workflow in an autonomous agent because that would
hide the hardest part: building reliable data and tool boundaries.

The mature design decision was:

```text
deterministic system first
  -> explicit state and provenance
  -> measurable ingestion and review workflow
  -> AI only where ambiguity exists
  -> human approval before outputs are trusted
```

An agent is valuable only after the core tools are reliable. In this project, the
future agent would call bounded operations such as `search_sources`,
`enrich_sources`, `export_source_packet`, and `corpus_metrics`. It would not get
unrestricted filesystem access or silently rewrite the knowledge base.

That is the point of the demo: not "AI everywhere", but production-oriented judgment
about where AI should sit in an automation system.

## Architecture

```text
OneTab / Markdown / CSV / text exports
  -> parsers
  -> URL normalization
  -> deduplication
  -> SQLite repository
  -> search + review web console
  -> enrichment draft provider
  -> human review
  -> metrics + Markdown source packets
```

The model-facing layer is deliberately isolated:

```text
URL record metadata
  -> enrichment provider interface
  -> draft JSON output
  -> pending_review status
  -> approve / reject with reviewer note
```

AI enrichment never mutates the canonical URL record directly.

## Evidence From The Real Corpus

The private corpus stays local and is not committed. It was used to validate that
the tool handles real messiness rather than only toy data.

Observed private-corpus smoke metrics:

| Metric | Value |
|---|---:|
| Input records processed | 8,448 |
| Valid URL occurrences | 8,420 |
| Unique URL records | 4,842 |
| Source occurrences | 8,420 |
| Dedupe rate | 42.49% |
| Ingest failures tracked | 28 |

The metrics report uses counts, domains, IDs, statuses, and basenames only. It does
not print raw private URL lists.

## Security And Privacy Boundary

This project is local-first by design.

- Private URL dumps and SQLite databases stay under ignored local directories.
- No `.env`, API keys, generated databases, raw exports, logs, or private outputs
  are committed.
- Public demos should use `samples/public_urls.csv`.
- AI enrichment is optional and mock-backed by default.
- Enrichment output is stored separately from canonical URL records.
- Draft source packets are marked as pending human review.
- CI includes a guard against accidentally tracking private or generated artifacts.

## CI/CD Signal

GitHub Actions runs on every push and pull request to `main`.

The pipeline checks:

- Python tests;
- Ruff linting;
- whitespace safety;
- private/generated artifact guard;
- Docker image build;
- demo database seed from public sample data;
- container smoke tests for `/health`, `/`, `/sources`, and `/capture`.

This is the delivery story: the project is not only runnable locally; it has a
repeatable verification path.

## Run Locally

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m url_kb.cli ingest_batch samples/public_urls.csv --database-url sqlite:///./data/demo.sqlite3
.venv/bin/python -m url_kb.cli serve --database-url sqlite:///./data/demo.sqlite3 --host 127.0.0.1 --port 8000
```

Open:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/sources`
- `http://127.0.0.1:8000/capture`

## Run With Docker

```bash
docker compose --profile seed run --rm seed-demo
docker compose up --build url-kb
```

Open `http://127.0.0.1:8000/`.

## Demo Walkthrough

1. Open `/capture`.
2. Paste a OneTab-style or Markdown-style batch of links.
3. Preview parsed URLs and malformed lines.
4. Ingest the batch.
5. Search by topic or domain in `/sources`.
6. Open a record detail page to inspect metadata and provenance.
7. Run mock enrichment from the CLI if needed.
8. Review enrichment drafts in `/enrichments`.
9. Export a Markdown source packet for a research task.
10. Show CI and Docker as the delivery guardrails.

## Interview Positioning

This project is relevant to an AI transformation and automation role because it
shows the part that often determines whether AI tools become useful: intake,
structure, traceability, review, metrics, and safe delivery.

The same pattern maps to internal automation requests:

```text
messy input from users
  -> deterministic normalization
  -> structured state
  -> optional AI enrichment
  -> human review
  -> reusable output
  -> measurable pipeline
```

In an enterprise setting, the next steps would be:

- authenticated multi-user access;
- Postgres or Postgres plus pgvector;
- selective public-content fetching;
- background enrichment jobs;
- retrieval evaluation;
- read-only agent tools first;
- write tools behind approval;
- audit logs per tool call;
- deployment on ECS/Fargate, RDS, S3, SQS, Secrets Manager, and CloudWatch.

## Current Limits

This is not presented as a complete enterprise knowledge platform.

- It does not yet scrape and summarize full page content.
- It does not yet run semantic vector retrieval.
- It does not include multi-user auth.
- It does not expose an MCP server yet.
- It does not make real model calls by default.

Those are deliberate next steps, not hidden claims.

The implemented value is the reliable automation substrate: ingest, normalize,
deduplicate, store, search, review, measure, package, containerize, and verify.
