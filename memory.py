"""In-run memory helpers: short-term action history, page memory, export formats.

Responsibility:
- In-memory data formatting, action history windowing, and page visit tracking.
- Serialization of extracted records into JSON and CSV byte streams for user download.

What it must NOT do:
- Must not perform disk I/O or SQLite database writes (delegated to persistence.py).
- Must not invoke LLMs or execute browser interactions.

Next module to read:
- persistence.py (handles persistent disk-backed storage of extracted records).
"""

from __future__ import annotations

import csv
import io
import json

# Caps how many action_history entries ride in AgentState — and therefore in every
# planner/reflector prompt (graph.py's _recent_history_text slices the last 6 of
# these). Raise with care: it's a direct multiplier on LLM prompt size/cost.
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
    # Records can have different shapes (extract_text vs. extract_table vs.
    # screenshot results), so the column set is the union of every key seen across
    # all records; DictWriter fills any record missing a given key with an empty cell.
    fieldnames = sorted({key for record in records for key in record})
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(records)
    return buffer.getvalue().encode("utf-8")
