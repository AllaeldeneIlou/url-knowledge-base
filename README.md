# URL Knowledge Base

![CI status](https://github.com/AllaeldeneIlou/url-knowledge-base/actions/workflows/ci.yml/badge.svg)

Local-first URL ingestion and review console for turning browser tab dumps, Markdown
links, CSV exports, and text files into a searchable knowledge base.

Copyright (c) Allaeldene Ilou.

## Overview

URL Knowledge Base solves a small but common research problem: useful links are easy
to collect and hard to reuse. Browser tabs, OneTab exports, notes, and CSV files
often lose context, review state, and provenance.

This project converts those sources into structured records:

```text
URL collections
  -> parsers
  -> normalization
  -> deduplication
  -> SQLite persistence
  -> search, review, metrics, and source packets
```

The current implementation is a local MVP focused on reliable capture, traceability,
and review before adding heavier AI or agentic processing.

## Features

| Area | What it does |
|---|---|
| Clipboard capture | Paste OneTab-style Markdown links, mixed text, and bare URLs |
| Batch ingestion | Import supported CSV, Markdown, Logseq-style, and text corpus formats |
| Normalization | Canonicalize URLs, extract domains, and deduplicate records |
| Provenance | Track source file, format, section, row, line/block, label, and source type |
| Search | Filter records by keyword, domain, and review status |
| Record detail | Inspect canonical URL metadata, original URL, provenance, and enrichment drafts |
| Enrichment review | Store draft enrichment output separately and approve or reject with notes |
| Source packets | Export filtered records to Markdown for a research or documentation task |
| Metrics | Report corpus health, dedupe rate, ingest failures, domains, and review coverage |
| Delivery | Run locally, in Docker, and through GitHub Actions CI |

## Web Console

The web console is intentionally compact and operational.

- `Overview` shows aggregate corpus metrics without printing raw URL lists.
- `Sources` lists persisted URL records and supports query/domain/status filters.
- `Capture` accepts pasted browser-tab exports, previews parsed records, and ingests
  valid URLs into the database.
- `Enrichments` lists draft enrichment rows and supports approve/reject review
  decisions with reviewer notes.
- `Record detail` shows canonical metadata, provenance, and enrichment history for a
  single URL record.

## Architecture

The project is organized as a modular Python application:

```text
url_kb/
  ingest/      parsers, normalization, deduplication, clipboard capture
  storage/     SQLite repository and schema ownership
  search/      source search and URL review status updates
  enrich/      provider interface and draft enrichment workflow
  export/      Markdown source packet generation
  metrics/     aggregate corpus reporting
  web/         FastAPI review console
  cli.py       operational command line entrypoint
```

The enrichment layer is deliberately isolated from canonical URL records:

```text
URL record
  -> enrichment provider interface
  -> draft JSON output
  -> pending_review / approved / rejected
  -> human note
```

An enrichment draft never mutates the canonical URL record directly.

## AI And Agent Boundary

The current provider is mock-only by default. That is intentional: the core data
model, provenance, review states, and delivery pipeline are implemented before
connecting real model calls.

A future agentic layer should call bounded operations such as:

- `search_sources`
- `export_source_packet`
- `enrich_sources`
- `corpus_metrics`

It should not receive unrestricted filesystem access, silently rewrite canonical
records, delete data, or treat unreviewed model output as source truth.

## Security And Privacy

- Private URL dumps, generated databases, and output packets are ignored by Git.
- Public demos should use `samples/public_urls.csv`.
- The metrics view reports counts, domains, statuses, and basenames rather than raw
  private URL lists.
- AI enrichment output is stored separately from canonical records.
- Source packets are marked as draft material pending human review.
- CI checks that private/generated artifacts are not tracked.

## Run Locally

Create a virtual environment, install the package, seed the public sample, and start
the web console:

```bash
python -m venv .venv
.venv/bin/python -m pip install ".[dev]"
.venv/bin/python -m url_kb.cli ingest_batch samples/public_urls.csv --database-url sqlite:///./data/demo.sqlite3
.venv/bin/python -m url_kb.cli serve --database-url sqlite:///./data/demo.sqlite3 --host 127.0.0.1 --port 8000
```

Open:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/sources`
- `http://127.0.0.1:8000/capture`
- `http://127.0.0.1:8000/enrichments`

## Run With Docker

Seed the demo database and start the app:

```bash
docker compose --profile seed run --rm seed-demo
docker compose up --build url-kb
```

Open `http://127.0.0.1:8000/`.

## CLI Examples

```bash
url-kb search_sources --query python --database-url sqlite:///./data/demo.sqlite3
url-kb corpus_metrics --database-url sqlite:///./data/demo.sqlite3
url-kb export_source_packet --query python --output outputs/source_packets/python.md --database-url sqlite:///./data/demo.sqlite3
url-kb enrich_sources --query python --provider mock --limit 5 --database-url sqlite:///./data/demo.sqlite3
url-kb list_enrichments --status pending_review --database-url sqlite:///./data/demo.sqlite3
```

## CI/CD

GitHub Actions runs on pushes and pull requests to `main`.

The pipeline:

1. Installs the package with development dependencies.
2. Runs the Python test suite.
3. Runs Ruff linting.
4. Checks whitespace with `git diff --check`.
5. Fails if private/generated artifacts are tracked.
6. Builds the Docker image.
7. Seeds a demo SQLite database from the public sample.
8. Starts the container and smoke-tests `/health`, `/`, `/sources`, and `/capture`.

## Current Limits

This is not a full enterprise knowledge platform yet.

- It does not scrape and summarize full page content.
- It does not run semantic vector retrieval.
- It does not include multi-user authentication.
- It does not expose an MCP server.
- It does not make real model calls by default.

Those are natural extension points. The implemented scope is the reliable substrate:
capture, normalize, deduplicate, persist, search, review, measure, export,
containerize, and verify.
