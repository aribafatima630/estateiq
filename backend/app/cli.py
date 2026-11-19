from __future__ import annotations

import argparse
import asyncio

import uvicorn

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.ingestion.pipeline import run_scrape
from app.main import create_app
from app.services.runtime import build_runtime


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="EstateIQ commands")
    sub = parser.add_subparsers(dest="command", required=True)
    scrape = sub.add_parser("scrape")
    scrape.add_argument("--source", choices=["wasalt", "darglobal", "all"], default="all")
    sub.add_parser("index")
    sub.add_parser("serve")
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "serve":
        uvicorn.run(
            "app.main:create_app",
            factory=True,
            host=settings.host,
            port=settings.port,
            reload=False,
        )
        return
    runtime = build_runtime(settings)
    if args.command == "index":
        count = runtime.retrieval.rebuild()
        print(f"Indexed {count} chunks")
        return
    sources = None if args.source == "all" else [args.source]
    report = asyncio.run(
        run_scrape(settings, runtime.repository, runtime.retrieval, sources)
    )
    print(
        "records",
        report["records_extracted"],
        "pages",
        report["pages_scraped"],
        "errors",
        len(report["errors"]),
    )


if __name__ == "__main__":
    main()
