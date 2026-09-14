"""Environment-driven settings and LLM factories.

Responsibility:
- Parse and validate runtime environment variables and settings.
- Construct configured LangChain chat model instances (OpenAI, Agnes AI, Ollama).

What it must NOT do:
- Must not hardcode credentials or secrets in source code or defaults.
- Must not make LLM inference calls or execute browser actions directly.

Next module to read:
- graph.py (consumes LLM factory outputs for planner, actuator, and reflector nodes).
"""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()

DEFAULT_PLANNER_MODEL = os.environ.get("OPENAI_PLANNER_MODEL", "gpt-4o")
DEFAULT_VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", DEFAULT_PLANNER_MODEL)
DEFAULT_LOCAL_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")
DEFAULT_OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Agnes AI (https://www.agnes-ai.com/en/docs/overview) is OpenAI-compatible —
# same chat-completions shape, tool_calling, and image_url vision input — so it
# reuses ChatOpenAI directly instead of a custom wrapper.
AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
AGNES_MODEL = "agnes-2.5-flash"

CLOUD_PROVIDER_CHOICES = ("openai", "agnes")
DEFAULT_CLOUD_PROVIDER = os.environ.get("CLOUD_PROVIDER", "openai")

MAX_STEPS = int(os.environ.get("MAX_STEPS", "25"))
MEMORY_DB_PATH = os.environ.get("MEMORY_DB_PATH", "./agent_memory.db")

# Actions containing any of these words (case-insensitive) in their target text
# pause the graph for human approval before executing.
SENSITIVE_KEYWORDS = (
    "submit",
    "pay",
    "buy",
    "confirm",
    "purchase",
    "checkout",
    "place order",
)

LOCAL_MODEL_CHOICES = (
    "qwen3.5:9b",
    "qwen3.5:4b",
    "ministral-3:8b",
    "granite4.1:8b",
    "qwen2.5:7b",
    "llama3.1:8b",
)


@dataclass
class Settings:
    cloud_provider: str = DEFAULT_CLOUD_PROVIDER  # "openai" or "agnes"
    planner_model: str = DEFAULT_PLANNER_MODEL
    vision_model: str = DEFAULT_VISION_MODEL
    local_model: str = DEFAULT_LOCAL_MODEL
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    temperature_planner: float = 0.2
    temperature_local: float = 0.1
    max_steps: int = MAX_STEPS


def ollama_available(
    base_url: str = DEFAULT_OLLAMA_BASE_URL, timeout: float = 1.5
) -> bool:
    # Error boundary: probe local daemon connectivity with a short timeout.
    # Swallows all network/connection exceptions (ConnectionRefusedError, TimeoutError, etc.)
    # to return a binary availability flag without crashing caller startup.
    try:
        with urllib.request.urlopen(base_url, timeout=timeout):
            return True
    except Exception:  # noqa: BLE001 - health check; any failure means "unavailable"
        return False


def _require_openai_key() -> tuple[str, str | None]:
    # Invariant: OpenAI client initialization requires a non-empty key.
    # Raises RuntimeError early before starting execution loop if missing.
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    return api_key, os.environ.get("OPENAI_BASE_URL") or None


def _require_agnes_key() -> str:
    # Invariant: Agnes AI provider requires an explicit AGNES_API_KEY.
    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        raise RuntimeError("AGNES_API_KEY environment variable is not set.")
    return api_key


def get_planner_llm(settings: Settings) -> BaseChatModel:
    """Cloud model for high-level planning, reflection, and hard decisions."""
    from langchain_openai import ChatOpenAI

    if settings.cloud_provider == "agnes":
        return ChatOpenAI(
            model=AGNES_MODEL,
            temperature=settings.temperature_planner,
            api_key=_require_agnes_key(),
            base_url=AGNES_BASE_URL,
        )
    api_key, base_url = _require_openai_key()
    return ChatOpenAI(
        model=settings.planner_model,
        temperature=settings.temperature_planner,
        api_key=api_key,
        base_url=base_url,
    )


def get_vision_llm(settings: Settings) -> BaseChatModel:
    """Cloud model for screenshot understanding. Must be vision-capable."""
    from langchain_openai import ChatOpenAI

    if settings.cloud_provider == "agnes":
        return ChatOpenAI(
            model=AGNES_MODEL,
            temperature=0,
            api_key=_require_agnes_key(),
            base_url=AGNES_BASE_URL,
        )
    api_key, base_url = _require_openai_key()
    return ChatOpenAI(
        model=settings.vision_model,
        temperature=0,
        api_key=api_key,
        base_url=base_url,
    )


def get_local_llm(settings: Settings, model_name: str | None = None) -> BaseChatModel:
    """Local Ollama model for simple navigation/clicking/filling/extraction.

    reasoning=False disables "thinking" mode (Ollama's `think` param) — several
    local models default to it, and the multi-paragraph chain-of-thought they
    generate before every single tool call (measured: ~55s of generation for a
    one-word reply on qwen3.5:9b) defeats the point of routing simple actions to
    the local model for speed. GPT escalation already covers cases that need
    real reasoning.
    """
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=model_name or settings.local_model,
        temperature=settings.temperature_local,
        base_url=settings.ollama_base_url,
        reasoning=False,
    )
