# Tool-Using Browser Agent

An autonomous, tool-using browser agent built with **LangGraph**, **Playwright**, and **Streamlit** — it plans, acts, observes, and remembers its way through real web tasks like price comparison, form filling, and competitor research, with a human-in-the-loop safety gate before any sensitive action.

**Repository:** https://github.com/pypi-ahmad/tool-using-browser-agent

Free, open-source, and community-driven — clone it, run it on your own machine with your own API
keys, and use it however you like. Bug reports, feature ideas, and pull requests are genuinely
welcome; see [Contributing & Community](#contributing--community) below.

> [!IMPORTANT]
> This agent's planner and reflector always call a cloud LLM (OpenAI or Agnes AI), sending your
> task, open tab URLs, and truncated page-content summaries on every step — plus full screenshots
> when the vision fallback triggers. Only local Ollama handles the actual click/fill/navigate
> execution first. You are fully responsible for the sites you point this at and the data involved.
> Read [DISCLAIMER.md](DISCLAIMER.md) before running it on anything sensitive.

## Features

- **Full browser toolset** — `navigate`, `click`, `fill`, `extract_text`, `extract_table`, `extract_links`, `scroll`, `wait_for_selector`, `go_back`/`go_forward`, `screenshot`, and multi-tab control (`open_new_tab`, `switch_tab`, `list_tabs`, `close_tab`).
- **Multi-tab support** — the agent can open and work across several sites in parallel, each tab in its own isolated browser context.
- **Hybrid model routing** — simple, repetitive actions (click/fill/navigate) go to a fast local Ollama model; planning, reflection, and vision go to a cloud model (OpenAI-compatible, or [Agnes AI](https://www.agnes-ai.com/en/docs/overview)). If the local model fails to produce a valid tool call, the action is automatically escalated to the cloud model.
- **Vision fallback** — when a selector fails or the page looks broken (cookie banner, CAPTCHA, unfamiliar layout), the agent takes a screenshot and asks the vision model what to do next.
- **Short-term + persistent memory** — an in-run action history and structured extracted-data list, backed by a SQLite store that survives across app restarts and is searchable from the UI.
- **Human-in-the-loop approval** — any action that looks like a form submission or payment (keywords like "submit", "pay", "checkout", "place order") pauses the graph and waits for explicit Approve/Reject in the UI before executing.
- **Live, step-by-step UI** — the action log, open tabs, extracted data, and screenshot preview update incrementally as each graph node completes, not just once the whole task finishes.
- **Safety controls** — a configurable maximum step limit, a visible Stop button that halts the agent mid-run, and full action history for auditability.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | [Streamlit](https://streamlit.io/) |
| Agent orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) (StateGraph, checkpointing, `interrupt`/`Command` human-in-the-loop) |
| Browser automation | [Playwright](https://playwright.dev/python/) (async) |
| Local LLM | [Ollama](https://ollama.com/) via `langchain-ollama` |
| Cloud LLM | OpenAI-compatible API via `langchain-openai` (OpenAI, or [Agnes AI](https://www.agnes-ai.com/en/docs/agnes-25-flash)) |
| Persistence | SQLite (stdlib `sqlite3`, no ORM) |
| Package management | [uv](https://docs.astral.sh/uv/) |

## Project Structure

```
Tool-Using Browser Agent/
├── app.py                      # Streamlit UI + AgentRunner (background thread, live polling)
├── graph.py                    # LangGraph state, nodes, and routing (the agent's core loop)
├── tools/
│   └── browser_tools.py        # BrowserSession (multi-tab Playwright) + LangChain tool wrappers
├── memory.py                   # In-run short-term memory helpers (history trim, JSON/CSV export)
├── persistence.py              # SQLite-backed long-term memory (save/search/list)
├── vision.py                   # Screenshot -> vision-model analysis for stuck/broken pages
├── config.py                   # Environment-driven settings and LLM factories
├── utils.py                    # Small shared helpers (ids, base64, sensitive-action detection)
├── tests/                      # pytest suite (real headless-browser tests, no LLM required)
├── run.cmd                     # One-click setup + launch (Windows)
├── pyproject.toml / uv.lock    # Dependencies (uv)
└── .env.example                # Environment variable template
```

## How It Works

The agent is a [LangGraph](https://github.com/langchain-ai/langgraph) `StateGraph` with the following loop:

```
planner ─▶ (sensitive?) ─▶ human_approval ─▶ browser_actuator ─▶ observer
   ▲                              │                                  │
   │                       (rejected: skip)                          ▼
   │                                                          memory_updater
   │                                                                  │
   │                                                          persist_memory
   │                                                                  │
   └──────────────────────── reflector ◀────────────────────────────┘
                          (continue | finish)
```

Non-sensitive actions skip `human_approval` entirely (`planner → browser_actuator` directly);
only actions flagged sensitive enter the approval gate shown above.

- **`planner`** (cloud model) — reads the task, recent history, and live browser tab state, and decides the single next concrete action. Flags the action as sensitive if it looks like a submit/payment step.
- **`human_approval`** — only entered for sensitive actions. Uses LangGraph's `interrupt()` to pause the graph and surface the action for approval in the UI; resumes via `Command(resume="approve" | "reject")`.
- **`browser_actuator`** — translates the instruction into a concrete tool call. Tries the local Ollama model first (fast path); if it fails to produce a valid tool call, escalates to the cloud model. Catches Playwright errors and flags the step for vision analysis instead of crashing the run.
- **`observer`** — captures the resulting page state, and if a vision flag was raised, calls the vision model with a screenshot to get unstuck.
- **`memory_updater`** — deterministic (no LLM): trims short-term action history and appends new structured extractions.
- **`persist_memory`** — deterministic: writes new extracted records to SQLite every pass, so a mid-run Stop doesn't lose data.
- **`reflector`** (cloud model) — decides whether to continue, replan, or finish; also forces completion once the step limit is reached.

The Streamlit UI runs the agent in a background thread with its own asyncio event loop (Playwright requires this), and streams the graph with `astream(stream_mode="updates")` so the UI updates after every single node, not just when the whole multi-step task completes.

## Installation & Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Ollama](https://ollama.com/) running locally, with a tool-calling-capable model pulled (e.g. `ollama pull qwen2.5:7b`)
- An OpenAI-compatible API key (OpenAI itself, an OpenAI-compatible proxy, or Agnes AI)

### Windows: one-click setup

Double-click **`run.cmd`**. It will:
1. Check `uv` is installed.
2. Create `.env` from `.env.example` on first run.
3. Run `uv sync` to install dependencies.
4. Install the Playwright Chromium browser.
5. Launch the app at `http://localhost:8511`.

### Manual setup (any OS)

```bash
uv sync --all-groups
uv run playwright install chromium
cp .env.example .env   # then fill in your API key(s)
uv run streamlit run app.py --server.port 8511
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CLOUD_PROVIDER` | `openai` | `openai` or `agnes` — which cloud provider powers planning/reflection/vision |
| `OPENAI_API_KEY` | — | Required when `CLOUD_PROVIDER=openai` |
| `OPENAI_BASE_URL` | — | Optional, for OpenAI-compatible proxies |
| `OPENAI_PLANNER_MODEL` | `gpt-4o` | Model used for planning/reflection |
| `OPENAI_VISION_MODEL` | `gpt-4o` | Model used for screenshot analysis (must support vision) |
| `AGNES_API_KEY` | — | Required when `CLOUD_PROVIDER=agnes`. See [Agnes AI docs](https://www.agnes-ai.com/en/docs/overview) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Default local model (selectable in the UI) |
| `MAX_STEPS` | `25` | Default maximum agent steps per task (also adjustable in the UI) |
| `MEMORY_DB_PATH` | `./agent_memory.db` | SQLite file for persistent extracted data |

Both `OPENAI_API_KEY`/`OPENAI_BASE_URL` and `AGNES_API_KEY` are read from real environment variables first — `.env` is only a fallback for values not already set in your shell/system environment.

## Usage

1. Launch the app (`run.cmd` or `uv run streamlit run app.py`).
2. Enter a task, e.g. *"Compare iPhone 16 prices on Amazon and Flipkart"*.
3. Pick a local model, a cloud provider, and a step limit.
4. Click **Start** and watch the live action log, open tabs, and extracted data update as the agent works.
5. If the agent needs to submit a form or make a payment, it will pause and ask for **Approve**/**Reject**.
6. Use **Stop** to halt the run at any time.
7. Once finished, download the extracted data as JSON or CSV, or browse/search everything ever extracted in the **Persistent memory browser** panel.

### Example tasks

- "Compare iPhone 16 prices across Amazon and Flipkart."
- "Fill out the demo request form on example.com with test data." *(will pause for approval before submitting)*
- "Go to a competitor's pricing page and extract their plan names and prices."
- "Open three product pages in separate tabs and summarize their key specs."

## Configuration Options

- **Local model** — any Ollama model with tool-calling support (selectable in the UI; extend `LOCAL_MODEL_CHOICES` in `config.py`).
- **Cloud provider** — `openai` or `agnes`, selectable in the UI.
- **Max steps** — per-run safety cap on total agent steps.
- **Sensitive-action keywords** — edit `SENSITIVE_KEYWORDS` in `config.py` to change what triggers the approval gate.

## Testing

```bash
uv run pytest tests/ -v
```

The suite runs real headless-browser tests (multi-tab, locator resolution) and SQLite persistence roundtrips — no LLM or network access required.

## Future Improvements

- Parallel (concurrent, not just multi-tab-sequential) task execution across sites.
- Semantic/fuzzy search over persistent memory (SQLite FTS5 or a vector store).
- A persistent (non-in-memory) LangGraph checkpointer for durable, restart-safe approval flows.

## Contributing & Community

This project is free, open-source, and welcomes contributions of all sizes — bug reports, feature
suggestions, documentation fixes, and code. It's maintained in spare time with no formal process,
so don't overthink it: open an issue or a pull request.

| Resource | Purpose |
| --- | --- |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup, project layout, coding style, and how to submit a PR |
| [Issues](https://github.com/pypi-ahmad/tool-using-browser-agent/issues) | Bug reports and feature requests (templates provided for both) |
| [SUPPORT.md](SUPPORT.md) | Where to ask usage questions and what response time to expect |
| [SECURITY.md](SECURITY.md) | How to report a security issue privately, and known risks of an LLM-driven browser agent |

> [!NOTE]
> This project does not want or accept donations, sponsorships, or any other financial support, and
> never will. It's free to use and free to modify. If you'd like to give back, the most valuable
> thing you can do is contribute code, tests, docs, or a well-written bug report.

## Disclaimer

- **You run this on your own machine, with your own API keys.** There is no hosted version and no
  account system.
- **You are 100% responsible for the sites you point this at and the data involved.** The cloud
  planner receives your task, tab URLs, and truncated page content on every step; only local Ollama
  handles execution first.
- **AI-driven actions can be wrong.** The human-in-the-loop approval gate is a safety net, not a
  guarantee — review every approval prompt.
- **No warranty, no liability**, per the [MIT License](LICENSE) — use it at your own risk.

See [DISCLAIMER.md](DISCLAIMER.md) for the full version.

## License

[MIT](LICENSE)

<p align="center">Made with ❤️ by Ahmad Mujtaba</p>
