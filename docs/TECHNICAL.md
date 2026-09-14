# Technical reference

Technical reference covering the software stack, execution invariants, error-handling mechanisms, and persistence models.

## Technology stack

| Library / Tool | Primary location | Verification in code | Rationale based on implementation |
| --- | --- | --- | --- |
| `python` (>= 3.14) | `pyproject.toml` | `requires-python = ">=3.14"` | Base runtime for all application logic. |
| `streamlit` | `app.py` | Imports `streamlit as st` | Renders the web UI, input form, live log view (`st.fragment`), and export buttons. |
| `langgraph` | `graph.py` | Imports `StateGraph`, `interrupt`, `Command`, `InMemorySaver` | Provides state graph construction, execution checkpoints, and human approval interrupts. |
| `playwright` (async) | `tools/browser_tools.py` | Imports `async_playwright`, `Page`, `Locator` | Manages headless Chromium instances, tab isolation, and DOM element actions. |
| `langchain-ollama` | `config.py` | Imports `ChatOllama` | Drives local inference via Ollama for tool calls with `reasoning=False`. |
| `langchain-openai` | `config.py` | Imports `ChatOpenAI` | Standard client used for both OpenAI and Agnes AI cloud completion endpoints. |
| `pandas` | `pyproject.toml` | Listed in project dependencies | Used by Streamlit for rendering tabular records. |
| `python-dotenv` | `config.py` | Imports `load_dotenv` | Loads environment configurations from `.env` on startup. |
| `sqlite3` | `persistence.py` | Imports `sqlite3` | Built-in standard library database engine used for persistence without external database servers. |
| `uv` | `run.cmd`, `pyproject.toml` | Referenced in setup commands and `uv.lock` | Python environment and dependency manager. |
| `pytest` / `pytest-asyncio` | `pyproject.toml` | Defined in `[dependency-groups] dev` | Test runner and async plugin for asynchronous testing. Runs 15 unit tests covering browser tools, graph routing, and SQLite persistence. |
| `ruff` | `pyproject.toml` | Defined in `[dependency-groups] dev` | Fast linter configured for development code verification. |
| `ty` | `pyproject.toml` | Defined in `[dependency-groups] dev` | Static type checker configured for development code verification. |

## Important invariants

1. **Asyncio loop affinity for browser processes:**
   Playwright asynchronous objects (`Browser`, `BrowserContext`, `Page`) cannot be shared across different asyncio event loops. `AgentRunner` (`app.py`) starts a single background daemon thread, binds a new event loop to it, and executes all browser tasks on that dedicated loop until completion.

2. **Main thread UI isolation:**
   Streamlit UI operations (`st.*`) must never be called from worker threads. `AgentRunner` synchronizes state changes to internal attributes guarded by `threading.Lock`. The main Streamlit thread reads these attributes through `AgentRunner.snapshot()` using an auto-refreshing fragment (`@st.fragment(run_every="1s")`).

3. **Isolated browser contexts per tab:**
   In `tools/browser_tools.py`, `BrowserSession.open_new_tab()` calls `self.browser.new_page()`. In Playwright, `new_page()` on a `Browser` instance creates an isolated context. As a result, storage states, cookies, and cache are isolated between distinct tabs.

4. **Multi-layer sensitive action detection:**
   Before a browser action executes, `route_after_planner` evaluates whether the action must be gated:
   - Check 1: The structured output `PlannerDecision.sensitive` boolean emitted by the planning model.
   - Check 2: String matching against `SENSITIVE_KEYWORDS` (`"submit"`, `"pay"`, `"buy"`, `"confirm"`, `"purchase"`, `"checkout"`, `"place order"`) in `utils.py::is_sensitive_text`.
   If either condition evaluates to true, execution diverts to `human_approval`.

5. **Tiered model routing with fallback:**
   `browser_actuator_node` binds available browser tools to the local Ollama model first. If the local model returns an empty list of `tool_calls`, the prompt immediately escalates to the cloud planner model.

6. **Bounded context history:**
   To prevent context window overflow, `memory.py::trim_history` restricts `action_history` to `ACTION_HISTORY_LIMIT` (15 entries). In addition, `graph.py::_recent_history_text` slices only the most recent 6 entries when constructing prompt strings for the planner and reflector.

7. **Incremental persistence watermark:**
   `persist_memory_node` tracks `persisted_count` in `AgentState`. On each pass of the agent loop, only records at index `state["extracted_data"][state["persisted_count"]:]` are inserted into SQLite. If a user interrupts or cancels a run, previously extracted records remain stored on disk.

## Error handling

- **Playwright and selector errors:**
  When a tool call raises `playwright.async_api.Error` (e.g. locator timeout or missing element) or `ValueError` (invalid `tab_id`), `browser_actuator_node` catches the exception, converts it to an error string in `last_observation`, and sets `needs_vision = True`. If an active tab exists, it attempts to capture a base64 screenshot.
- **Vision analysis fallback:**
  If `needs_vision` is active, `observer_node` forwards the screenshot and error to `vision.analyze_screenshot`. Any failure in the vision model API call is caught locally and returned as `"(vision analysis unavailable: {exc})"`, preventing vision API downtime from crashing the agent loop.
- **Missing API credentials:**
  Calling `_require_openai_key()` or `_require_agnes_key()` in `config.py` when the respective environment variable is unset raises a `RuntimeError`. This is caught by the outer try-block in `AgentRunner._run_async`, setting the runner status to `"error"` and surfacing the message in the UI via `st.error()`.
- **Unhandled worker exceptions:**
  Any unexpected exception in `AgentRunner._run_async` sets `self.status = "error"` and stores the exception string in `self.error`. The browser session is guaranteed to close in a `finally` block via `await session.close()`.

## Persistence paths

- **Database file location:**
  Stored on disk at the path defined by `MEMORY_DB_PATH` (default: `./agent_memory.db`).
- **Schema specification:**
  Defined in `persistence.py`:
  ```sql
  CREATE TABLE IF NOT EXISTS memory (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      session_id TEXT NOT NULL,
      task TEXT NOT NULL,
      url TEXT,
      type TEXT,
      data_json TEXT NOT NULL,
      created_at TEXT NOT NULL
  );
  ```
- **Write path:**
  On every graph loop iteration, `persist_memory_node` calls `persistence.save_record` for any new item in `state["extracted_data"]`. Content is serialized to JSON string format using `json.dumps(..., default=str)`.
- **Query path:**
  `persistence.search_memory` performs substring searches against `data_json`, `url`, and `task` using SQL `LIKE ?` with `%query%`. Results are sorted by `id DESC` up to a user-specified or default limit.
