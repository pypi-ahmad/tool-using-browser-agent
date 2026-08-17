# Technical Reference

Deeper architecture reference than the README's [How It Works](README.md#how-it-works) summary — for anyone extending the agent, adding a tool or provider, or debugging a run. See [USAGE.md](USAGE.md) for the how-to guide.

## What this is

A single-process Streamlit app plus a small Python package (no `src/` layout — modules live at the repo root). One LangGraph `StateGraph` drives the whole agent loop; a Playwright `BrowserSession` executes actions; SQLite persists extracted data across restarts. There is no backend server, no queue, and no multi-user support — one browser tab, one agent run, in one background thread.

## Module map

| Module | Responsibility |
| --- | --- |
| `app.py` | Streamlit UI, `AgentRunner` (owns the background thread + event loop), live polling via `st.fragment` |
| `graph.py` | `AgentState`, the LangGraph node functions, and the graph's edges/routing |
| `tools/browser_tools.py` | `BrowserSession` (multi-tab Playwright) and the `@tool`-wrapped functions the LLM calls |
| `config.py` | `Settings` dataclass, env-var defaults, and the three LLM factory functions |
| `memory.py` | In-run short-term memory: history trimming, page-visit tracking, JSON/CSV export |
| `persistence.py` | Disk-backed long-term memory: SQLite schema, save/search/list |
| `vision.py` | Screenshot → vision-model analysis, called only on the vision-fallback path |
| `utils.py` | Small shared helpers: ID generation, base64 encoding, sensitive-keyword matching |

## The LangGraph state machine

### State shape (`AgentState`, `graph.py`)

A single `TypedDict` carries everything between nodes: `task`, `next_action` (the planner's current decision), `tabs`/`active_tab` (mirrors the live browser session), `action_history` (trimmed to the last 15 entries by `memory.trim_history`), `extracted_data` (append-only), `persisted_count` (watermark for what's already written to SQLite), `page_memory` (URL → last-visited timestamp), `last_observation`, `needs_vision`/`screenshot_b64`, `step_count`/`max_steps`, `session_id`, and `status` (`"running" | "paused_for_approval" | "done" | "stopped" | "error"`).

### Nodes, in graph order

1. **`planner_node`** — always uses the cloud model (`planner_llm`, never Ollama). Reads live tab state directly from the `BrowserSession` (not `state["tabs"]`, which lags by one step) plus the last 6 action-history entries, and returns a structured `PlannerDecision` (`instruction`, `sensitive`, `reasoning`) via `with_structured_output`. `sensitive` is OR'd with a keyword check (`is_sensitive_text`) so either the model's own judgment or a literal keyword match can trigger approval.
2. **`route_after_planner`** — `human_approval` if `next_action.sensitive`, else straight to `browser_actuator`. This is the branch the README's diagram doesn't draw explicitly — see the caption under the diagram there.
3. **`human_approval_node`** — calls LangGraph's `interrupt()` with the instruction and reasoning, pausing the graph until `Command(resume="approve"|"reject")` is sent from the UI. On rejection, it clears `next_action`, increments `step_count`, and records a synthetic `last_observation` with `error="action rejected by human approval"` — the run continues, it doesn't abort.
4. **`route_after_approval`** — `browser_actuator` if approved (`next_action` still set), else `observer` directly (skipping execution entirely on rejection).
5. **`browser_actuator_node`** — tries the **local Ollama model first** (`local_llm.bind_tools(...)`), with `reasoning=False` forced in `config.get_local_llm` because several local models default to "thinking" mode and burn ~55s generating chain-of-thought before a single tool call. If the local model produces no tool call, it **escalates to the cloud planner model** with the same messages. Catches `PlaywrightError`/`ValueError` from the actual tool execution and sets `needs_vision=True` plus captures a screenshot on failure.
6. **`observer_node`** — reads the current page URL, and if `needs_vision` was set, calls `vision.analyze_screenshot` with the cloud vision model and the failed instruction, attaching the guidance text to the observation.
7. **`memory_updater_node`** — deterministic, no LLM call. Appends a trimmed history entry; if the last tool was one of `EXTRACTION_TOOLS = {"extract_text", "extract_table", "extract_links", "screenshot"}` and didn't error, appends a new `extracted_data` record; marks the visited URL in `page_memory`.
8. **`persist_memory_node`** — deterministic. Writes only the *new* slice of `extracted_data` (`state["extracted_data"][state["persisted_count"]:]`) to SQLite on every pass, not just at the end — so a mid-run Stop doesn't lose already-extracted records.
9. **`reflector_node`** — always cloud model. Force-finishes (`status="done"`) once `step_count >= max_steps` without an LLM call; otherwise asks the model for a structured `ReflectorDecision(finished, reasoning)`.
10. **`route_after_reflector`** — back to `planner` unless `status == "done"`, in which case `END`.

The graph is compiled with `InMemorySaver()` as its checkpointer — state does not survive a process restart mid-run (see [Known limitations](#known-limitations)).

## Model routing — what actually runs where

| Node | Model | Notes |
| --- | --- | --- |
| `planner_node` | Cloud (always) | `get_planner_llm` — never Ollama |
| `browser_actuator_node` | Ollama first, cloud on tool-call failure | The only node that tries local first |
| `observer_node` (vision path only) | Cloud vision model | Only called when `needs_vision` is set |
| `reflector_node` | Cloud (always) | `get_planner_llm` again — reflection reuses the planner model |

Both cloud factories (`get_planner_llm`, `get_vision_llm`) route through the same two branches in `config.py`: `cloud_provider == "agnes"` builds a `ChatOpenAI` pointed at Agnes AI's fixed base URL and model (`AGNES_BASE_URL`, `AGNES_MODEL = "agnes-2.5-flash"`); otherwise it's a standard OpenAI-compatible call using `OPENAI_API_KEY`/`OPENAI_BASE_URL` and the configured model name. See [DISCLAIMER.md](DISCLAIMER.md) for exactly what content this sends off-machine.

## `BrowserSession` — multi-tab and locator resolution

Each call to `open_new_tab` calls `browser.new_page()`, which creates a **fresh, isolated `BrowserContext`** per tab (not one shared context with multiple pages) — so cookies/storage never leak between tabs, matching the "separate context per tab" design goal.

Locators are resolved through a fallback chain rather than a single CSS selector, so the LLM can refer to elements by their visible text:

- **Clickable elements** (`_resolve_clickable`): ARIA `link` role → ARIA `button` role → substring text match → raw selector as a last resort.
- **Input elements** (`_resolve_input`): label → placeholder → `textbox` role → `searchbox` role → raw selector.

`_first_visible` guards every candidate with a visibility check before accepting it, so a hidden duplicate element earlier in the DOM doesn't get picked over a visible one later.

## Memory: short-term vs. long-term

- **`memory.py`** — pure in-graph state helpers, no I/O beyond the export functions. `ACTION_HISTORY_LIMIT = 15` caps how much history rides in `AgentState` (and therefore in every planner/reflector prompt).
- **`persistence.py`** — one SQLite table (`memory`), plain stdlib `sqlite3`, no ORM. `search_memory` is a substring `LIKE` match against `data_json`, `url`, and `task` — explicitly not semantic/fuzzy search (see the module's own `ponytail:` comment noting SQLite FTS5 as the upgrade path if that's ever needed).

## Vision fallback

Triggered only when a tool call raises `PlaywrightError`/`ValueError`, or when no valid tool call was produced at all. `vision.analyze_screenshot` sends the full screenshot plus the failed instruction and task to the cloud vision model, and degrades to a short `"(vision analysis unavailable: {exc})"` string instead of raising if the vision call itself fails — vision is best-effort, not a hard dependency for the graph to keep running.

## Concurrency model

Streamlit's script re-runs on every interaction, so the agent can't run on the main thread. `AgentRunner` (`app.py`) spawns one daemon thread per run, creates a **fresh asyncio event loop** inside that thread (Playwright's async API requires the same loop for the life of the browser), and exposes a `threading.Lock`-guarded `snapshot()` for the UI to poll. The UI's `st.fragment(run_every="1s")` re-renders just the live-view fragment while a run is active, without re-running the whole script. `graph.astream(..., stream_mode="updates")` yields a partial-state dict after every single node finishes, which is what makes the action log update step-by-step instead of only once the whole task completes.

## Extension points

- **New browser tool** — add a method to `BrowserSession`, then wrap it with `@tool` in `build_tools()`. The tool's docstring is what the LLM sees as its description, so write it for the model, not for a human reader.
- **New LLM provider** — follow the `agnes`-vs-default branch pattern in `config.py`'s `get_planner_llm`/`get_vision_llm`; add the provider to `CLOUD_PROVIDER_CHOICES` and wire its API key check into a new `_require_<provider>_key()` function.
- **New local model choice** — add it to `LOCAL_MODEL_CHOICES` in `config.py`; it appears in the UI dropdown automatically.
- **New sensitive-action rule** — add a keyword to `SENSITIVE_KEYWORDS`, or extend `is_sensitive_text`/the planner's own `sensitive` field for non-keyword-based detection.

## Known limitations

- **`InMemorySaver()` checkpointing does not survive a process restart** — a mid-run Stop or crash loses in-graph state (though already-extracted records are safe in SQLite, since `persist_memory_node` runs every pass).
- **The approval gate is keyword/model-judgment based, not a hard policy** — see [SECURITY.md](SECURITY.md) for the specific risk this creates.
- **The routing/short-circuit logic is unit-tested (`tests/test_graph_routing.py`) with no LLM or network calls, including a `_PoisonLLM` fixture that asserts `reflector_node` never calls the model once `max_steps` is reached** — but the LLM-calling nodes themselves (`planner_node`, `browser_actuator_node`'s escalation path, `observer_node`'s vision path) have no automated coverage.
