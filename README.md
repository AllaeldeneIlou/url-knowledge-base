# URL Knowledge Base

Local-first URL capture, ingestion, review, and retrieval tool.

The private working corpus stays local. Public demos should use sanitized sample data only.

## Local Run

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

## Docker

Build and seed a sanitized demo database:

```bash
docker compose --profile seed run --rm seed-demo
docker compose up --build url-kb
```

Open `http://127.0.0.1:8000/`.

## CI/CD

GitHub Actions runs:

- tests;
- ruff;
- whitespace checks;
- private artifact guard;
- Docker image build;
- demo database seed;
- container smoke tests for `/health`, `/`, `/sources`, and `/capture`.

## Privacy Boundary

Do not commit:

- `.env` or secrets;
- SQLite databases;
- `data/`;
- generated `outputs/`;
- private browser exports;
- raw URL dumps.

The real private corpus can be ingested locally with `ingest_private_corpus`, but the deployed/demo version should use sanitized sample data.
