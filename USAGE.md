# Usage

A step-by-step how-to guide. For how the agent works internally, see [TECHNICAL.md](TECHNICAL.md).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed.
- [Ollama](https://ollama.com/) running locally, with a tool-calling-capable model pulled (e.g. `ollama pull qwen3.5:9b`).
- An OpenAI or [Agnes AI](https://www.agnes-ai.com/en/docs/overview) API key.

## Install and launch

**Windows — one click:**

Double-click `run.cmd`. It checks for `uv`, copies `.env.example` to `.env` on first run, syncs dependencies, installs the Playwright Chromium browser, and opens the app at `http://localhost:8511`.

**Manual (any OS):**

```bash
uv sync --all-groups
uv run playwright install chromium
cp .env.example .env   # then fill in your API key(s)
uv run streamlit run app.py --server.port 8511
```

Set your credentials before launching (see [README.md — Environment Variables](README.md#environment-variables)) — the app reads real environment variables first, and only falls back to `.env` for anything not already set.

## The task form

When you open the app, you get a form with four controls:

| Control | What it does |
| --- | --- |
| **Task** | Plain-language description of what you want done, e.g. *"Compare iPhone 16 prices on Amazon and Flipkart"*. |
| **Local model (Ollama)** | Which Ollama model handles the fast click/fill/navigate execution path. Dropdown of `LOCAL_MODEL_CHOICES` from `config.py`. |
| **Cloud model (planning/vision)** | `openai` or `agnes` — powers the planner, reflector, and vision fallback. |
| **Max steps** | Hard cap on total agent steps for this run (1–100, default 25). |

Click **Start**. The form disables itself and the live view appears once the run is active.

## Running a task

Once started, the agent loops: plan a step → (approval gate, if sensitive) → execute → observe → update memory → persist → reflect → repeat, until it decides it's done or hits the step limit. You don't need to do anything while it runs, unless it pauses for approval (below).

The **live view** updates after every single step, not just at the end:

- **Action log** — every step so far, newest first, with a ✅/❌ marker and the instruction. Steps with an error show the error text underneath.
- **Open tabs** — every tab the agent has opened, with its current URL.
- **Latest screenshot** — only shown when the vision fallback has fired (a selector failed, or the page looked broken).
- **Extracted data** — a live table of everything the agent has pulled off pages so far (`extract_text`, `extract_table`, `extract_links`, or `screenshot` results).

## The human-in-the-loop approval gate

If the planner flags a step as sensitive — or the instruction contains a keyword like "submit", "pay", "buy", "confirm", "purchase", "checkout", or "place order" — the run pauses. You'll see:

> **Approval needed:** *the exact instruction the agent wants to execute*
>
> Reasoning: *the model's stated reason*

Click **Approve** to let it proceed, or **Reject** to skip that one action (the run continues to the next planning step either way — rejecting doesn't stop the whole task).

> [!IMPORTANT]
> The keyword list and the model's own judgment are the only things gating this. Read every approval prompt — don't approve on autopilot, especially for anything involving money or an account. See [DISCLAIMER.md](DISCLAIMER.md).

## Stopping a run

Click **Stop** at any time. The agent checks for the stop request between steps (and mid-stream, between graph nodes) and halts as soon as it notices — it may finish the in-flight step first rather than stopping instantly mid-action.

## Downloading results

Once a run reaches a terminal state (done, stopped, or error) and has extracted at least one record, two download buttons appear:

- **Download JSON** — the full extracted-data list, indented.
- **Download CSV** — the same data as a flat CSV (columns are the union of all record keys across all rows).

## Persistent memory browser

At the bottom of the page, the **Persistent memory browser** expander lets you look at *every* extracted record from *every* run ever made on this machine — not just the current session. Type a search term (it matches against the URL, the task description, or the extracted data itself) to filter, or leave it blank to see the 50 most recent records.

This reads from the same SQLite file (`agent_memory.db` by default, configurable via `MEMORY_DB_PATH`) that `persist_memory_node` writes to during every run — so results from a run you stopped halfway through are already there.

## Example tasks

- *"Compare iPhone 16 prices across Amazon and Flipkart."* — exercises multi-tab, `extract_text`/`extract_table`, and cross-tab summarization.
- *"Fill out the demo request form on example.com with test data."* — will pause for approval before the submit step.
- *"Go to a competitor's pricing page and extract their plan names and prices."* — single-tab extraction task.
- *"Open three product pages in separate tabs and summarize their key specs."* — tests `open_new_tab`/`switch_tab` across more than two tabs.
- *"Search for a laptop under $1000 on a shopping site and list the top 5 results with prices."* — combines `fill` (search box), `extract_table` or `extract_text`, and a numeric constraint the planner has to reason about.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Run fails immediately with a missing-key error | `OPENAI_API_KEY`/`AGNES_API_KEY` not set for the selected cloud provider | Set the key as a real environment variable, or fill in `.env` and restart the app |
| Every action escalates to the cloud model | Local Ollama model isn't tool-calling-capable, or isn't running | Confirm `ollama list` shows the model, and that it's one known to support tool calls |
| Agent seems stuck repeating the same failed action | The vision fallback couldn't identify the right element, or the page needs a login/CAPTCHA it can't pass | Click **Stop**, check the **Latest screenshot**, and consider a task that doesn't require passing that gate |
| **Start** button does nothing | Task field was empty or only whitespace | Enter a non-empty task before clicking Start |
| App shows "Approval needed" but you didn't expect it | The planner flagged the action `sensitive`, or the instruction text happened to contain a gate keyword | This is working as intended — review and Approve/Reject |
| Extracted data table is empty at the end | No `extract_text`/`extract_table`/`extract_links`/`screenshot` call succeeded during the run | Check the action log for errors on extraction steps |
| Persistent memory browser shows nothing for a search term | The term doesn't literally appear in the URL, task, or extracted JSON | Search is a substring match, not fuzzy/semantic — try a shorter or different term |
