from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    location TEXT,
    price REAL,
    property_type TEXT,
    attributes TEXT NOT NULL DEFAULT '{}',
    source_url TEXT NOT NULL,
    scraped_at TEXT NOT NULL,
    city TEXT,
    country TEXT,
    currency TEXT,
    purpose TEXT,
    bedrooms INTEGER,
    bathrooms INTEGER,
    area_sqm REAL,
    published_at TEXT,
    content_hash TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_records_source_url
    ON records (source, source_url);
CREATE INDEX IF NOT EXISTS idx_records_category ON records (category);
CREATE INDEX IF NOT EXISTS idx_records_city ON records (city);
CREATE INDEX IF NOT EXISTS idx_records_type ON records (property_type);
CREATE INDEX IF NOT EXISTS idx_records_price ON records (price);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    report TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    source_filter TEXT,
    last_record_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, created_at);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self.conn.execute(sql, params)
            self.conn.commit()
            return cursor

    def executemany(self, sql: str, seq: list[tuple]) -> None:
        with self._lock:
            self.conn.executemany(sql, seq)
            self.conn.commit()

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self.conn.execute(sql, params))
