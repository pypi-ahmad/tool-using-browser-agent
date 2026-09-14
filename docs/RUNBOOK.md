# Runbook

Operational reference for starting, stopping, observing, and troubleshooting the tool-using browser agent.

## Starting the application

### Windows automated setup

Run the batch script from the repository root:

```cmd
run.cmd
```

The script verifies that `uv` exists on the system path, copies `.env.example` to `.env` if `.env` does not exist, runs `uv sync --all-groups`, installs the Playwright Chromium browser binaries, and executes `uv run streamlit run app.py --server.port 8511`.

### Manual startup (any platform)

Execute the following commands in order:

```bash
uv sync --all-groups
uv run playwright install chromium
cp .env.example .env
uv run streamlit run app.py --server.port 8511
```

*Note for Windows Command Prompt:* Replace `cp .env.example .env` with `copy .env.example .env`.

Before starting an agent task, edit `.env` or set environment variables to provide valid credentials (`OPENAI_API_KEY` or `AGNES_API_KEY`). Ensure an Ollama daemon is running and has the designated local model pulled (e.g. `ollama pull qwen3.5:9b`).

## Stopping the application

### Halting an active task

Click the **Stop** button in the Streamlit user interface.
- Mechanism: Calls `AgentRunner.request_stop()`, which toggles `_stop_requested = True`.
- Timing: The agent checks this flag at the beginning of each loop and within streaming chunk updates. The active Playwright action completes before the run transitions to `status="stopped"`.

### Terminating the server process

Press `Ctrl+C` in the terminal where Streamlit was launched, or close the terminal window.
- The browser and background thread are child threads/processes of the main Streamlit process. When the main process exits, background resources terminate. Active browser tabs are closed during clean termination via `BrowserSession.close()`.

## Log output and observation

There is no custom logging configuration or log file created by default (no `import logging` exists in application modules).

- **Standard console output:** Streamlit and Playwright output stdout and stderr directly to the terminal running the application. Uncaught exceptions and stack traces appear here.
- **In-app action log:** Displayed in the Streamlit UI under the **Action log** section. Backed by `AgentState["action_history"]`. Records step indices, tool names, instructions, and error summaries. This log is in-memory only and clears upon page refresh or process restart.
- **Extracted records:** Stored permanently in the SQLite database specified by `MEMORY_DB_PATH` (`./agent_memory.db`). Inspectable in the UI via the **Persistent memory browser** panel.

## Common failures and troubleshooting

| Error string or symptom | Source in codebase | Root cause | Remediation |
| --- | --- | --- | --- |
| `OPENAI_API_KEY environment variable is not set.` | `config.py::_require_openai_key` | `CLOUD_PROVIDER` is set to `openai` (default) but `OPENAI_API_KEY` is empty or missing. | Export `OPENAI_API_KEY` in shell environment or define it in `.env`, then restart the server. |
| `AGNES_API_KEY environment variable is not set.` | `config.py::_require_agnes_key` | `CLOUD_PROVIDER` is set to `agnes` but `AGNES_API_KEY` is empty or missing. | Export `AGNES_API_KEY` in shell environment or define it in `.env`, then restart the server. |
| `uv not found - install from https://docs.astral.sh/uv/` | `run.cmd` | `uv` executable is missing from system `PATH`. | Install `uv` and ensure its binary directory is added to the system path. |
| `Unknown tab_id: <tab_id>` | `tools/browser_tools.py::BrowserSession._page` | The model called a tool referencing a tab identifier that does not exist or was closed. | The error is recorded in the action log; the planner will receive this failure observation and attempt recovery on subsequent turns. |
| `no tool call produced (local model, then GPT escalation, both failed)` | `graph.py::browser_actuator_node` | Both the local model and cloud planner model failed to output a structured tool call for the given instruction. | Confirm that the local model supports tool calling (e.g. `qwen3.5:9b`, `qwen2.5:7b`). If using cloud escalation, verify API connectivity. |
| `unknown tool: <tool_name>` | `graph.py::browser_actuator_node` | The model generated a tool call with a name not present in `tools_by_name`. | The failure is captured in `last_observation` and reported back to the planner on the next turn. |
| `(vision analysis unavailable: <error>)` | `vision.py::analyze_screenshot` | The vision model API invocation failed (e.g., API rate limit, invalid key, or model lacks vision support). | Execution continues without vision guidance. Verify that `OPENAI_VISION_MODEL` or the selected provider supports image input. |
| Playwright browser executable missing | Playwright invocation in `tools/browser_tools.py` | Chromium binary was not installed prior to startup. | Run `uv run playwright install chromium`. |
| Ollama connection refused / timeout | `config.py::ollama_available` | Local Ollama service is not running on `OLLAMA_HOST`. | Start the Ollama daemon (`ollama serve`) or verify the port on `http://localhost:11434`. |
