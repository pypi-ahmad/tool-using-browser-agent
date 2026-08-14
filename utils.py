"""Small shared helpers used across modules."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

from config import SENSITIVE_KEYWORDS


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def bytes_to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def is_sensitive_text(text: str) -> bool:
    """True if the action's target text/reason looks like a submit/payment step."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
