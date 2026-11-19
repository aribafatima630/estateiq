from __future__ import annotations

import asyncio
import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.prompts import UNKNOWN_ANSWER
from app.schemas.api import ChatRequest, ChatResponse, HealthResponse, StatsResponse
from app.services.runtime import Runtime

router = APIRouter(prefix="/api")


def get_runtime() -> Runtime:
    raise RuntimeError("Runtime dependency was not configured")


def require_admin(
    x_admin_token: str | None = Header(default=None),
    runtime: Runtime = Depends(get_runtime),
) -> None:
    expected = runtime.settings.admin_token
    if not expected:
        raise HTTPException(status_code=503, detail="Admin token is not configured")
    provided = x_admin_token or ""
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/health", response_model=HealthResponse)
def health(runtime: Runtime = Depends(get_runtime)) -> HealthResponse:
    counts = runtime.repository.counts()
    return HealthResponse(
        status="ok",
        database=True,
        index_ready=runtime.retrieval.index.ready,
        records=counts["records"],
        llm_configured=runtime.llm.configured,
        scraper_enabled=runtime.settings.scraper_enabled,
    )


@router.get("/stats", response_model=StatsResponse)
def stats(runtime: Runtime = Depends(get_runtime)) -> StatsResponse:
    counts = runtime.repository.counts()
    last = runtime.repository.latest_run()
    return StatsResponse(
        records=counts["records"],
        chunks=len(runtime.retrieval.index.metas),
        by_source=counts["by_source"],
        by_category=counts["by_category"],
        index_ready=runtime.retrieval.index.ready,
        llm_configured=runtime.llm.configured,
        resolved_model=runtime.llm.resolved_model,
        last_scrape=last,
    )


@router.get("/sources")
def sources(runtime: Runtime = Depends(get_runtime)) -> dict:
    counts = runtime.repository.counts()["by_source"]
    return {
        "sources": [
            {
                "id": "darglobal",
                "name": "DarGlobal",
                "url": "https://darglobal.co.uk/",
                "kind": "Luxury real estate developer",
                "records": counts.get("darglobal", 0),
            },
            {
                "id": "wasalt",
                "name": "Wasalt",
                "url": "https://wasalt.sa/en",
                "kind": "Saudi property marketplace",
                "records": counts.get("wasalt", 0),
            },
        ]
    }


@router.get("/properties")
def properties(
    city: str | None = None,
    property_type: str | None = None,
    purpose: str | None = None,
    bedrooms: int | None = None,
    max_price: float | None = None,
    source: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    rows = runtime.repository.list_records(
        source=source,
        category="property",
        city=city,
        property_type=property_type,
        purpose=purpose,
        bedrooms=bedrooms,
        max_price=max_price,
        currency="SAR" if max_price is not None else None,
        limit=limit,
    )
    return {"properties": rows, "count": len(rows)}


@router.get("/projects")
def projects(
    location: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    rows = runtime.repository.list_records(
        source="darglobal",
        category="project",
        location=location,
        limit=limit,
    )
    return {"projects": rows, "count": len(rows)}


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, runtime: Runtime = Depends(get_runtime)) -> ChatResponse:
    return runtime.chat.answer(body.message, body.session_id, body.source_filter)


@router.get("/chat/history")
def history(session_id: str | None = None, runtime: Runtime = Depends(get_runtime)) -> dict:
    if session_id:
        session = runtime.repository.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session": session, "messages": runtime.repository.list_messages(session_id)}
    return {"sessions": runtime.repository.list_sessions()}


@router.delete("/chat/history/{session_id}")
def delete_history(session_id: str, runtime: Runtime = Depends(get_runtime)) -> dict:
    deleted = runtime.repository.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}


@router.post("/scrape/run")
def scrape_run(
    source: str | None = None,
    _: None = Depends(require_admin),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    if not runtime.settings.scraper_enabled:
        raise HTTPException(status_code=403, detail="Scraping is disabled on this deployment")
    sources = [source] if source in {"wasalt", "darglobal"} else None
    run_id = uuid.uuid4().hex

    def job() -> None:
        asyncio.run(
            __import__("app.ingestion.pipeline", fromlist=["run_scrape"]).run_scrape(
                runtime.settings,
                runtime.repository,
                runtime.retrieval,
                sources,
                run_id,
            )
        )

    if not runtime.jobs.start(job):
        raise HTTPException(status_code=409, detail="A scrape or index job is already running")
    return {"status": "started", "run_id": run_id}


@router.get("/scrape/status")
def scrape_status(runtime: Runtime = Depends(get_runtime)) -> dict:
    return {"running": runtime.jobs.running, "last_run": runtime.repository.latest_run()}


@router.post("/index/rebuild")
def rebuild_index(
    _: None = Depends(require_admin),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    def job() -> None:
        runtime.retrieval.rebuild()

    if not runtime.jobs.start(job):
        raise HTTPException(status_code=409, detail="A scrape or index job is already running")
    return {"status": "started"}


@router.get("/meta/refusal")
def refusal() -> dict:
    return {"unknown_answer": UNKNOWN_ANSWER}
