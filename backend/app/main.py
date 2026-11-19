from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import get_runtime, router
from app.core.config import Settings
from app.core.logging import configure_logging
from app.services.runtime import build_runtime


def _frontend_dir() -> Path | None:
    here = Path(__file__).resolve()
    for path in (here.parents[1] / "static", here.parents[2] / "frontend" / "dist"):
        if (path / "index.html").is_file():
            return path
    return None


def create_app(settings: Settings | None = None, embedder=None, llm=None) -> FastAPI:
    configure_logging()
    runtime = build_runtime(settings=settings, embedder=embedder, llm=llm)
    app = FastAPI(title="EstateIQ", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.settings.cors_origin_list or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.include_router(router)
    frontend = _frontend_dir()
    if frontend is not None:
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    app.state.runtime = runtime
    return app
