"""Small shared helpers used across modules.

Responsibility:
- Pure, dependency-light utility functions (ID generation, base64 encoding, timestamp generation, sensitive text matching).

What it must NOT do:
- Must not perform network I/O, database queries, or LLM calls.
- Must not depend on higher-level modules (app, graph, tools).

Next module to read:
- persistence.py or tools/browser_tools.py (primary consumers of these helpers).
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

from config import SENSITIVE_KEYWORDS


def new_id(prefix: str) -> str:
    # Generates a short prefixed identifier (e.g., 'tab-a1b2c3d4').
    # Uses 8 hex characters (32 bits of entropy), sufficient for local session and tab uniqueness.
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def bytes_to_b64(data: bytes) -> str:
    # Encodes raw screenshot bytes to ASCII base64 for JSON serialization and data URIs.
    return base64.b64encode(data).decode("ascii")


def is_sensitive_text(text: str) -> bool:
    """True if the action's target text/reason looks like a submit/payment step.

    Security boundary: evaluates untrusted model instruction strings against
    SENSITIVE_KEYWORDS. Substring match is case-insensitive.
    """
    lowered = text.lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def utc_now_iso() -> str:
    # ISO-8601 with UTC offset (e.g. "2024-01-01T00:00:00+00:00"). This exact string
    # is stored as-is (not reparsed) in persistence.py's `created_at` column and in
    # every action_history entry graph.py builds — keep the format stable.
    return datetime.now(UTC).isoformat()
