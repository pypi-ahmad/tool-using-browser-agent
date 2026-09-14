# Tool-using browser agent

Tool-using browser agent is a local-first web automation agent that executes browser-based tasks through a LangGraph state machine. It uses a local Ollama model to execute tool actions (navigation, clicking, text entry, and data extraction) and escalates to a cloud model (OpenAI or Agnes AI) for high-level task planning, reflection, and screenshot vision analysis. Automation runs via Playwright in headless Chromium with isolated browser contexts per tab, extracted tabular and text data is saved to a local SQLite database, and sensitive operations pause for human approval through a Streamlit web interface.

## Requirements

Runtime requirements derived from `pyproject.toml`, `run.cmd`, and source modules:

- **Python:** Version `>=3.14` (specified in `pyproject.toml`).
- **Package manager:** [uv](https://docs.astral.sh/uv/) (pinned via `uv.lock`).
- **Browser binary:** Chromium managed by Playwright (`uv run playwright install chromium`).
- **Local inference:** [Ollama](https://ollama.com/) accessible via HTTP (default: `http://localhost:11434`) with a tool-calling capable model available (default: `qwen3.5:9b`).
- **Cloud API credentials:** An API key for either OpenAI (`OPENAI_API_KEY`) or Agnes AI (`AGNES_API_KEY`).
- **Operating system:** Python source modules and CLI commands are platform-agnostic. The optional `run.cmd` script is Windows-specific.

## Setup and run

### Automated launch (Windows)

On Windows systems, execute the batch script from the repository root:

```cmd
run.cmd
```

This script checks for `uv`, creates `.env` from `.env.example` if `.env` does not exist, runs `uv sync --all-groups`, installs Playwright Chromium, and starts the Streamlit server on port `8511`.

### Manual launch (all platforms)

1. Synchronize project dependencies:
   ```bash
   uv sync --all-groups
   ```
2. Install the Playwright Chromium browser:
   ```bash
   uv run playwright install chromium
   ```
3. Initialize the environment configuration file:
   ```bash
   cp .env.example .env
   ```
   *(On Windows Command Prompt, use `copy .env.example .env`)*
4. Configure API keys in `.env` (see the configuration section below).
5. Start the Streamlit application:
   ```bash
   uv run streamlit run app.py --server.port 8511
   ```
   Access the web interface at `http://localhost:8511`.

## Configuration

Configuration values are loaded from environment variables and `.env` via `python-dotenv` in `config.py`.

| Variable | Default value | Purpose |
| --- | --- | --- |
| `CLOUD_PROVIDER` | `openai` | Cloud LLM provider for planning, reflection, and vision (`openai` or `agnes`). |
| `OPENAI_API_KEY` | None | API key for OpenAI. Required if `CLOUD_PROVIDER=openai`. |
| `OPENAI_BASE_URL` | None | Optional custom base URL for OpenAI-compatible proxies. |
| `OPENAI_PLANNER_MODEL` | `gpt-4o` | Model identifier used for planning and reflection. |
| `OPENAI_VISION_MODEL` | `gpt-4o` | Model identifier used for screenshot analysis (must support image inputs). |
| `AGNES_API_KEY` | None | API key for Agnes AI. Required if `CLOUD_PROVIDER=agnes` (endpoint: `https://apihub.agnes-ai.com/v1`, model: `agnes-2.5-flash`). |
| `OLLAMA_HOST` | `http://localhost:11434` | HTTP address of the local Ollama server. |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Default local model for actuator tool calls. UI choices: `qwen3.5:9b`, `qwen3.5:4b`, `ministral-3:8b`, `granite4.1:8b`, `qwen2.5:7b`, `llama3.1:8b`. |
| `MAX_STEPS` | `25` | Maximum execution steps allowed per run before forcing task termination. |
| `MEMORY_DB_PATH` | `./agent_memory.db` | File path for the persistent SQLite database storing extracted data records. |

In addition to environment variables, `config.py` defines `SENSITIVE_KEYWORDS` (`"submit"`, `"pay"`, `"buy"`, `"confirm"`, `"purchase"`, `"checkout"`, `"place order"`), which automatically route actions to the human approval gate.

## Repository map

Important directories and files in the repository:

```
.
├── app.py                # Streamlit web interface and AgentRunner background worker thread
├── config.py             # Settings dataclass, environment variable resolution, and LLM factories
├── graph.py              # LangGraph state definition, node implementations, and routing edges
├── memory.py             # In-memory history bounding and JSON/CSV export helpers
├── persistence.py        # SQLite schema initialization, record insertion, and search operations
├── utils.py              # Identifiers, base64 conversion, and sensitive keyword evaluation
├── vision.py             # Screenshot encoding and cloud vision model query logic
├── run.cmd               # Windows batch setup and launcher script
├── pyproject.toml        # Project dependencies, packaging metadata, and tool configuration
├── uv.lock               # Pinned dependency lockfile
├── .env.example          # Environment variable template
├── docs/                 # Detailed system documentation
│   ├── ARCHITECTURE.md   # State machine, request flows, and component diagram
│   ├── CONTRIBUTING.md   # Contribution guidelines, development setup, and code checks
│   ├── RUNBOOK.md        # Operations, execution instructions, and error lookup table
│   └── TECHNICAL.md      # Technical stack rationale, invariants, and persistence paths
└── tools/
    ├── __init__.py       # Package marker
    └── browser_tools.py  # Playwright BrowserSession and LangChain tool wrappers
```

## How to run tests

Test dependencies are declared in `pyproject.toml` under `[dependency-groups] dev` (`pytest>=9.1.1` and `pytest-asyncio>=1.4.0`), with `[tool.pytest.ini_options]` setting `asyncio_mode = "auto"`.

To invoke the test suite:

```bash
uv run pytest
```

*Verification status:* The test suite in `tests/` contains 15 unit tests covering browser tool operations, graph conditional routing, and persistence storage. Running `uv run pytest` executes and passes all 15 tests.

## Known limitations

- **Process restart state loss:** LangGraph checkpointer is initialized as `InMemorySaver()`. In-flight agent graph state does not survive application crashes or restarts. Extracted records persisted to SQLite are preserved.
- **Approval gate heuristics:** Sensitive action gating depends on string keyword matching (`SENSITIVE_KEYWORDS`) and model-declared booleans (`PlannerDecision.sensitive`), which do not guarantee detection of all consequential web actions.
- **Mandatory external cloud dependency:** High-level planning (`planner_node`) and reflection (`reflector_node`) require an external OpenAI or Agnes AI API key; purely local operation using Ollama alone is not supported.
- **Substring persistence search:** `persistence.py::search_memory` uses SQL `LIKE %...%` wildcard matching over serialized JSON, URLs, and task descriptions rather than indexed full-text or vector search.
- **Static type diagnostics:** Running `uv run ty check .` yields 8 diagnostic messages in `graph.py`, `persistence.py`, and `tools/browser_tools.py`.
- **Platform script limitation:** `run.cmd` is compatible only with Windows command interpreters. Other operating systems must run the manual commands listed in the setup section.

## Documentation links

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/TECHNICAL.md](docs/TECHNICAL.md)
- [docs/RUNBOOK.md](docs/RUNBOOK.md)
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)
