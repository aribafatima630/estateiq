from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import Settings
from app.database.repository import Repository
from app.rag.retrieval import RetrievalService
from app.schemas.records import Record
from app.scrapers.darglobal import scrape_darglobal
from app.scrapers.wasalt import scrape_wasalt
from app.utils.text import utc_now

logger = logging.getLogger(__name__)


async def run_scrape(
    settings: Settings,
    repository: Repository,
    retrieval: RetrievalService,
    sources: list[str] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    selected = sources or ["wasalt", "darglobal"]
    started = utc_now()
    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started,
        "finished_at": None,
        "urls_discovered": {},
        "pages_scraped": {},
        "pages_failed": {},
        "records_extracted": {},
        "records_unchanged": {},
        "records_per_source": {},
        "errors": [],
        "warnings": [],
        "failed_urls": [],
        "index_chunks": 0,
        "last_successful_scrape": None,
    }
    if run_id:
        repository.save_run(run_id, started, "running", report)
    scrapers = {
        "wasalt": scrape_wasalt,
        "darglobal": scrape_darglobal,
    }
    collected: list[Record] = []
    for name in selected:
        scraper = scrapers.get(name)
        if scraper is None:
            report["warnings"].append(f"Unknown source: {name}")
            continue
        try:
            records, stats = await scraper(settings)
        except Exception as exc:
            logger.exception("%s scrape failed", name)
            report["errors"].append(f"{name} scrape failed: {exc}")
            report["urls_discovered"][name] = 0
            report["pages_scraped"][name] = 0
            report["pages_failed"][name] = 0
            continue
        collected.extend(records)
        report["urls_discovered"][name] = stats.get("urls_discovered", 0)
        report["pages_scraped"][name] = stats.get("pages_scraped", 0)
        report["pages_failed"][name] = stats.get("pages_failed", 0)
        report["warnings"].extend(stats.get("warnings") or [])
        report["errors"].extend(stats.get("errors") or [])
        report["failed_urls"].extend(stats.get("failed_urls") or [])

    inserted = {"wasalt": 0, "darglobal": 0}
    unchanged = {"wasalt": 0, "darglobal": 0}
    for record in collected:
        try:
            status = repository.upsert_record(record)
        except Exception as exc:
            report["errors"].append(f"Could not store {record.source_url}: {exc}")
            continue
        _write_raw(settings, record)
        if status == "unchanged":
            unchanged[record.source] = unchanged.get(record.source, 0) + 1
        else:
            inserted[record.source] = inserted.get(record.source, 0) + 1
    report["records_extracted"] = inserted
    report["records_unchanged"] = unchanged
    report["records_per_source"] = repository.counts()["by_source"]
    if collected:
        try:
            report["index_chunks"] = retrieval.rebuild()
            report["last_successful_scrape"] = utc_now()
        except Exception as exc:
            logger.exception("Index rebuild failed")
            report["errors"].append(f"Index rebuild failed: {exc}")
    elif repository.counts()["records"]:
        report["warnings"].append("No new pages were scraped. The previous index was left unchanged.")
    report["finished_at"] = utc_now()
    status = "failed" if report["errors"] and not collected else "completed_with_errors" if report["errors"] else "completed"
    if run_id:
        repository.save_run(run_id, started, status, report, report["finished_at"])
    settings.report_path.parent.mkdir(parents=True, exist_ok=True)
    settings.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Scrape %s: %s", status, report["records_extracted"])
    return report


def _write_raw(settings: Settings, record: Record) -> None:
    path = settings.raw_dir / record.source / f"{record.id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
