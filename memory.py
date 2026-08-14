"""In-run memory helpers: short-term action history, page memory, export formats.

Disk-backed long-term storage lives in persistence.py — this module only touches
in-graph state for the duration of one run.
"""

from __future__ import annotations

import csv
import io
import json

ACTION_HISTORY_LIMIT = 15


def trim_history(entries: list[dict], limit: int = ACTION_HISTORY_LIMIT) -> list[dict]:
    return entries[-limit:] if len(entries) > limit else entries


def mark_visited(
    page_memory: dict[str, dict], url: str, timestamp: str
) -> dict[str, dict]:
    updated = dict(page_memory)
    updated[url] = {"last_visited": timestamp}
    return updated


def to_json(records: list[dict]) -> str:
    return json.dumps(records, indent=2, default=str)


def to_csv_bytes(records: list[dict]) -> bytes:
    if not records:
        return b""
    buffer = io.StringIO()
    fieldnames = sorted({key for record in records for key in record})
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(records)
    return buffer.getvalue().encode("utf-8")
