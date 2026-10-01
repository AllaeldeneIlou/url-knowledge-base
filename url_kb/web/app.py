from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from url_kb.enrich.service import (
    EnrichmentNotFoundError,
    list_enrichments,
    review_enrichment,
)
from url_kb.metrics.service import corpus_metrics
from url_kb.search.service import search_sources
from url_kb.storage.sqlite_repo import SQLiteURLRepository, StoredAIEnrichment

DEFAULT_WEB_DATABASE_URL = "sqlite:///./data/url_kb.sqlite3"

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="URL Knowledge Base")
    app.state.database_url = (
        database_url
        or os.environ.get("URL_KB_DATABASE_URL")
        or os.environ.get("URL_KB_PRIVATE_DATABASE_URL")
        or DEFAULT_WEB_DATABASE_URL
    )
    app.mount(
        "/static",
        StaticFiles(directory=WEB_DIR / "static"),
        name="static",
    )

    @app.get("/")
    def overview(request: Request):
        repository = _repository(request)
        metrics = corpus_metrics(repository)
        return templates.TemplateResponse(
            request,
            "overview.html",
            {
                "active": "overview",
                "metrics": metrics.to_dict(),
            },
        )

    @app.get("/sources")
    def sources(
        request: Request,
        query: str | None = None,
        domain: str | None = None,
        review_status: str | None = None,
    ):
        repository = _repository(request)
        result = search_sources(
            repository,
            query=_blank_to_none(query),
            domain=_blank_to_none(domain),
            review_status=_blank_to_none(review_status),
        )
        return templates.TemplateResponse(
            request,
            "sources.html",
            {
                "active": "sources",
                "records": result.records,
                "count": result.count,
                "filters": {
                    "query": query or "",
                    "domain": domain or "",
                    "review_status": review_status or "",
                },
            },
        )

    @app.get("/sources/{record_id}")
    def source_detail(request: Request, record_id: int):
        repository = _repository(request)
        repository.initialize()
        record = repository.get_url_record(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"URL record not found: {record_id}")

        occurrence_map = repository.list_source_occurrences_for_record_ids([record_id])
        enrichments = [
            _enrichment_for_template(enrichment)
            for enrichment in repository.list_ai_enrichments_for_url_record_id(record_id)
        ]
        return templates.TemplateResponse(
            request,
            "source_detail.html",
            {
                "active": "sources",
                "record": record,
                "occurrences": occurrence_map.get(record_id, []),
                "enrichments": enrichments,
            },
        )

    @app.get("/enrichments")
    def enrichments(
        request: Request,
        status: str | None = None,
        provider: str | None = None,
        limit: int = 50,
    ):
        repository = _repository(request)
        result = list_enrichments(
            repository,
            status=_blank_to_none(status),
            provider=_blank_to_none(provider),
            limit=limit,
        )
        return templates.TemplateResponse(
            request,
            "enrichments.html",
            {
                "active": "enrichments",
                "items": result.enrichments,
                "count": result.count,
                "filters": {
                    "status": status or "",
                    "provider": provider or "",
                    "limit": limit,
                },
            },
        )

    @app.post("/enrichments/{enrichment_id}/review")
    async def review_enrichment_action(request: Request, enrichment_id: int):
        form = parse_qs((await request.body()).decode("utf-8"))
        status = _form_value(form, "status")
        note = _blank_to_none(_form_value(form, "note"))
        next_url = _form_value(form, "next") or "/enrichments"
        try:
            review_enrichment(
                _repository(request),
                enrichment_id=enrichment_id,
                status=status,
                reviewer_note=note,
            )
        except (EnrichmentNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        return RedirectResponse(next_url, status_code=303)

    return app


def _repository(request: Request) -> SQLiteURLRepository:
    return SQLiteURLRepository.from_database_url(request.app.state.database_url)


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _form_value(form: dict[str, list[str]], name: str) -> str:
    values = form.get(name)
    if not values:
        return ""
    return values[0]


def _enrichment_for_template(enrichment: StoredAIEnrichment) -> dict[str, object]:
    payload = asdict(enrichment)
    try:
        output = json.loads(enrichment.output_json)
    except json.JSONDecodeError:
        output = {"raw": enrichment.output_json}
    payload["output"] = output
    return payload


app = create_app()
