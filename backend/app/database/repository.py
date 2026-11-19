from __future__ import annotations

import json
from typing import Any

from app.database.db import Database
from app.schemas.records import Record


RECORD_COLUMNS = (
    "id",
    "source",
    "title",
    "content",
    "category",
    "location",
    "price",
    "property_type",
    "attributes",
    "source_url",
    "scraped_at",
    "city",
    "country",
    "currency",
    "purpose",
    "bedrooms",
    "bathrooms",
    "area_sqm",
    "published_at",
    "content_hash",
)


def row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    raw_attributes = data.get("attributes") or "{}"
    if isinstance(raw_attributes, str):
        try:
            data["attributes"] = json.loads(raw_attributes)
        except json.JSONDecodeError:
            data["attributes"] = {}
    return data


class Repository:
    def __init__(self, database: Database):
        self.db = database

    def upsert_record(self, record: Record) -> str:
        existing = self.db.query("SELECT id, content_hash FROM records WHERE id = ?", (record.id,))
        if existing and existing[0]["content_hash"] == record.content_hash:
            self.db.execute(
                "UPDATE records SET scraped_at = ? WHERE id = ?",
                (record.scraped_at, record.id),
            )
            return "unchanged"
        payload = (
            record.id,
            record.source,
            record.title,
            record.content,
            record.category,
            record.location,
            record.price,
            record.property_type,
            json.dumps(record.attributes, ensure_ascii=False),
            record.source_url,
            record.scraped_at,
            record.city,
            record.country,
            record.currency,
            record.purpose,
            record.bedrooms,
            record.bathrooms,
            record.area_sqm,
            record.published_at,
            record.content_hash,
        )
        assignments = ", ".join(f"{column} = excluded.{column}" for column in RECORD_COLUMNS if column != "id")
        columns = ", ".join(RECORD_COLUMNS)
        placeholders = ", ".join("?" for _ in RECORD_COLUMNS)
        self.db.execute(
            f"""
            INSERT INTO records ({columns}) VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET {assignments}
            """,
            payload,
        )
        return "updated" if existing else "inserted"

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        rows = self.db.query("SELECT * FROM records WHERE id = ?", (record_id,))
        return row_to_dict(rows[0]) if rows else None

    def get_records(self, record_ids: list[str]) -> list[dict[str, Any]]:
        if not record_ids:
            return []
        placeholders = ", ".join("?" for _ in record_ids)
        rows = self.db.query(
            f"SELECT * FROM records WHERE id IN ({placeholders})",
            tuple(record_ids),
        )
        by_id = {row["id"]: row_to_dict(row) for row in rows}
        return [by_id[record_id] for record_id in record_ids if record_id in by_id]

    def list_records(
        self,
        *,
        source: str | None = None,
        category: str | None = None,
        city: str | None = None,
        property_type: str | None = None,
        purpose: str | None = None,
        bedrooms: int | None = None,
        max_price: float | None = None,
        min_price: float | None = None,
        currency: str | None = None,
        location: str | None = None,
        title_query: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if city:
            clauses.append("(lower(city) LIKE ? OR lower(location) LIKE ? OR lower(country) LIKE ?)")
            token = f"%{city.lower()}%"
            params.extend([token, token, token])
        if location and not city:
            clauses.append("(lower(location) LIKE ? OR lower(city) LIKE ? OR lower(country) LIKE ?)")
            token = f"%{location.lower()}%"
            params.extend([token, token, token])
        if property_type:
            clauses.append("lower(property_type) LIKE ?")
            params.append(f"%{property_type.lower()}%")
        if purpose:
            clauses.append("lower(purpose) = ?")
            params.append(purpose.lower())
        if bedrooms is not None:
            clauses.append("bedrooms = ?")
            params.append(bedrooms)
        if min_price is not None:
            clauses.append("price IS NOT NULL AND price >= ?")
            params.append(min_price)
        if max_price is not None:
            clauses.append("price IS NOT NULL AND price <= ?")
            params.append(max_price)
        if currency and (min_price is not None or max_price is not None):
            clauses.append("upper(currency) = ?")
            params.append(currency.upper())
        if title_query:
            clauses.append("(lower(title) LIKE ? OR lower(content) LIKE ?)")
            token = f"%{title_query.lower()}%"
            params.extend([token, token])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        rows = self.db.query(
            f"""
            SELECT * FROM records
            {where}
            ORDER BY
                CASE WHEN price IS NULL THEN 1 ELSE 0 END,
                price ASC,
                scraped_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        return [row_to_dict(row) for row in rows]

    def latest_news(self, source: str | None = None, limit: int = 6) -> list[dict[str, Any]]:
        clauses = ["category = 'news'"]
        params: list[Any] = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        params.append(limit)
        rows = self.db.query(
            f"""
            SELECT * FROM records
            WHERE {' AND '.join(clauses)}
            ORDER BY
                CASE WHEN published_at IS NULL OR published_at = '' THEN 1 ELSE 0 END,
                published_at DESC,
                scraped_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        return [row_to_dict(row) for row in rows]

    def distinct_places(self, source: str, category: str | None = None) -> list[str]:
        clauses = ["source = ?", "location IS NOT NULL", "location != ''"]
        params: list[Any] = [source]
        if category:
            clauses.append("category = ?")
            params.append(category)
        rows = self.db.query(
            f"""
            SELECT location, COUNT(*) AS total
            FROM records
            WHERE {' AND '.join(clauses)}
            GROUP BY location
            ORDER BY total DESC, location ASC
            """,
            tuple(params),
        )
        return [row["location"] for row in rows]

    def counts(self) -> dict[str, Any]:
        total = self.db.query("SELECT COUNT(*) AS total FROM records")[0]["total"]
        by_source = {
            row["source"]: row["total"]
            for row in self.db.query("SELECT source, COUNT(*) AS total FROM records GROUP BY source")
        }
        by_category = {
            row["category"]: row["total"]
            for row in self.db.query("SELECT category, COUNT(*) AS total FROM records GROUP BY category")
        }
        return {"records": total, "by_source": by_source, "by_category": by_category}

    def all_records(self) -> list[dict[str, Any]]:
        return [row_to_dict(row) for row in self.db.query("SELECT * FROM records ORDER BY source, category, title")]

    def priced_count(self, source: str) -> int:
        rows = self.db.query(
            "SELECT COUNT(*) AS total FROM records WHERE source = ? AND price IS NOT NULL",
            (source,),
        )
        return int(rows[0]["total"])

    def save_run(self, run_id: str, started_at: str, status: str, report: dict[str, Any], finished_at: str | None = None) -> None:
        self.db.execute(
            """
            INSERT INTO scrape_runs (id, started_at, finished_at, status, report)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                finished_at = excluded.finished_at,
                status = excluded.status,
                report = excluded.report
            """,
            (run_id, started_at, finished_at, status, json.dumps(report, ensure_ascii=False)),
        )

    def latest_run(self) -> dict[str, Any] | None:
        rows = self.db.query(
            "SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 1"
        )
        if not rows:
            return None
        data = dict(rows[0])
        try:
            data["report"] = json.loads(data.get("report") or "{}")
        except json.JSONDecodeError:
            data["report"] = {}
        return data

    def create_session(self, session_id: str, title: str, source_filter: str | None, now: str) -> None:
        self.db.execute(
            """
            INSERT INTO sessions (id, title, source_filter, last_record_ids, created_at, updated_at)
            VALUES (?, ?, ?, '[]', ?, ?)
            """,
            (session_id, title, source_filter, now, now),
        )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        rows = self.db.query("SELECT * FROM sessions WHERE id = ?", (session_id,))
        if not rows:
            return None
        data = dict(rows[0])
        try:
            data["last_record_ids"] = json.loads(data.get("last_record_ids") or "[]")
        except json.JSONDecodeError:
            data["last_record_ids"] = []
        return data

    def update_session(
        self,
        session_id: str,
        *,
        source_filter: str | None,
        last_record_ids: list[str],
        now: str,
        title: str | None = None,
    ) -> None:
        if title is None:
            self.db.execute(
                """
                UPDATE sessions
                SET source_filter = ?, last_record_ids = ?, updated_at = ?
                WHERE id = ?
                """,
                (source_filter, json.dumps(last_record_ids), now, session_id),
            )
            return
        self.db.execute(
            """
            UPDATE sessions
            SET title = ?, source_filter = ?, last_record_ids = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, source_filter, json.dumps(last_record_ids), now, session_id),
        )

    def add_message(
        self,
        message_id: str,
        session_id: str,
        role: str,
        content: str,
        payload: dict[str, Any] | None,
        created_at: str,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO messages (id, session_id, role, content, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                role,
                content,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                created_at,
            ),
        )

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC, rowid ASC",
            (session_id,),
        )
        messages: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if item.get("payload"):
                try:
                    item["payload"] = json.loads(item["payload"])
                except json.JSONDecodeError:
                    item["payload"] = None
            messages.append(item)
        return messages

    def property_type_counts(self, source: str | None = None) -> list[dict[str, Any]]:
        if source:
            rows = self.db.query(
                """
                SELECT source, property_type, COUNT(*) AS n
                FROM records
                WHERE property_type IS NOT NULL AND property_type != '' AND source = ?
                GROUP BY source, property_type
                ORDER BY n DESC
                """,
                (source,),
            )
        else:
            rows = self.db.query(
                """
                SELECT source, property_type, COUNT(*) AS n
                FROM records
                WHERE property_type IS NOT NULL AND property_type != ''
                GROUP BY source, property_type
                ORDER BY n DESC
                """
            )
        return [dict(row) for row in rows]

    def list_sessions(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT id, title, source_filter, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        existing = self.get_session(session_id)
        if not existing:
            return False
        self.db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return True
