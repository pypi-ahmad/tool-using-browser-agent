"""Disk-backed long-term memory. Outlives the process. Plain stdlib sqlite3, no ORM.

Responsibility:
- Manage the SQLite database connection and schema for long-term memory.
- Provide CRUD functions: insert extracted records, search by keyword LIKE match, and list recent records.

What it must NOT do:
- Must not manage browser state or LangGraph execution loops.
- Must not perform vector embeddings or semantic search (plain substring LIKE match only).

Next module to read:
- graph.py (see persist_memory_node, the sole writer of persisted records).
- app.py (see Persistent memory browser, the consumer of search_memory and list_recent).
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
    # Fresh connection per call, closed immediately after — no pooling, no shared
    # long-lived connection. Schema creation is idempotent (CREATE TABLE IF NOT
    # EXISTS) so it's safe to run on every connect rather than once at startup.
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
        # Malformed/non-JSON data_json (shouldn't happen via save_record, but the
        # column has no CHECK constraint) — surface the raw string instead of
        # failing the whole read.
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
                # default=str: falls back to str() for anything json can't serialize
                # natively, so an odd extraction result never blocks the write.
                json.dumps(record.get("data"), default=str),
                record["created_at"],
            ),
        )
        return cursor.lastrowid


def search_memory(
    query: str, limit: int = 20, db_path: str = MEMORY_DB_PATH
) -> list[dict]:
    # Search boundary: simple SQL substring LIKE matching across json content, url, and task.
    # ASCII matching is case-insensitive in SQLite by default. Results are ordered newest first (id DESC).
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
