"""Disk-backed long-term memory. Outlives the process. Plain stdlib sqlite3, no ORM.

Search is a plain substring LIKE match, not semantic — nothing in the spec asks
for ranked/fuzzy recall, only "search and retrieve".
ponytail: upgrade path is SQLite FTS5 if fuzzy/ranked search is ever wanted.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from config import MEMORY_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    task TEXT NOT NULL,
    url TEXT,
    type TEXT,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def _connect(db_path: str = MEMORY_DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    record = dict(row)
    raw = record.pop("data_json", None)
    try:
        record["data"] = json.loads(raw) if raw is not None else None
    except ValueError:
        record["data"] = raw
    return record


def save_record(record: dict, db_path: str = MEMORY_DB_PATH) -> int:
    with _connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO memory (session_id, task, url, type, data_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                record["session_id"],
                record["task"],
                record.get("url"),
                record.get("type"),
                json.dumps(record.get("data"), default=str),
                record["created_at"],
            ),
        )
        return cursor.lastrowid


def search_memory(
    query: str, limit: int = 20, db_path: str = MEMORY_DB_PATH
) -> list[dict]:
    like = f"%{query}%"
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM memory WHERE data_json LIKE ? OR url LIKE ? OR task LIKE ? "
            "ORDER BY id DESC LIMIT ?",
            (like, like, like, limit),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_recent(limit: int = 50, db_path: str = MEMORY_DB_PATH) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM memory ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_sessions(db_path: str = MEMORY_DB_PATH) -> list[str]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT session_id FROM memory ORDER BY id DESC"
        ).fetchall()
    return [row["session_id"] for row in rows]
