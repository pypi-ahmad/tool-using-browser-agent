# Contributing to Tool-Using Browser Agent

Thanks for considering a contribution — this is a small, community-driven, hobby-scale project, and every bug report, suggestion, and pull request genuinely helps.

There's no formal process here. If something feels like overkill for the size of a change you want to make, it probably is — just open an issue or a PR and we'll figure it out together.

## Ways to contribute

- **Report a bug** — open an issue using the bug report template.
- **Suggest a feature** — open an issue using the feature request template. The [Future Improvements](README.md#future-improvements) list in the README is a good place to check first for ideas already on the radar.
- **Improve the docs** — README.md and this guide are both fair game.
- **Submit code** — bug fixes, new browser tools, new LLM providers, small features. See below.

## Before you start coding

For anything beyond a trivial fix, open an issue first (or comment on an existing one) describing what you want to change and why. This avoids duplicate work and lets us agree on the approach before you invest time in it.

Do not include real API keys, browsing session data, or scraped personal data in an issue or pull request.

## Development setup

```bash
git clone https://github.com/pypi-ahmad/tool-using-browser-agent.git
cd tool-using-browser-agent
uv sync --all-groups
uv run playwright install chromium
cp .env.example .env   # then fill in at least one provider key
uv run streamlit run app.py --server.port 8511
```

See [README.md](README.md#installation--setup) for prerequisites and [README.md](README.md#environment-variables) for the environment variables you'll need.

## Project layout

- `app.py` — Streamlit UI and `AgentRunner` (background thread, live polling). Business logic doesn't belong here.
- `graph.py` — the LangGraph state machine and its node functions. This is the agent's core loop.
- `tools/browser_tools.py` — `BrowserSession` (multi-tab Playwright) and the LangChain tool wrappers. No LLM/LangChain-model imports beyond the `@tool` decorator — keep it that way.
- `config.py` — `Settings` dataclass and the LLM provider factories.
- `memory.py` / `persistence.py` — in-run short-term memory vs. disk-backed long-term SQLite memory. Keep that boundary.
- `vision.py` — screenshot analysis, called only on the vision-fallback path.

## Coding style

There's no linter config or CI configured yet (no `.github/workflows`, no `ruff.toml`). Until that changes, please just match the style already in the file you're editing: type hints on function signatures, `from __future__ import annotations` at the top, and the existing docstring/comment conventions (a short module docstring explaining *why*, not *what*).

Run these before submitting, using their default configuration:

```bash
uv run ruff check .
uv run ty check .
uv run pytest tests/ -v
```

## Testing your change

The test suite (`tests/`) runs real headless-browser tests and SQLite persistence roundtrips — no LLM or network access required for those. If your change touches `graph.py`, `config.py`, or the LLM factories, also manually verify by actually running the app:

1. Run `uv run streamlit run app.py --server.port 8511`.
2. Give the agent a real task and confirm the change behaves as expected in the live action log.
3. If you touched the sensitive-action gate or a browser tool, confirm the human-in-the-loop approval prompt still triggers/skips correctly.

If you're adding a new browser tool, add it to `build_tools()` in `tools/browser_tools.py` and give it a clear docstring — the LLM sees that docstring as the tool's description. If you're adding a new LLM provider, follow the pattern in `config.py`'s existing `get_planner_llm`/`get_vision_llm`/`get_local_llm` factories.

## Submitting a pull request

- Keep PRs focused — one change per PR is much easier to review than five.
- Describe what you changed and why in the PR description.
- Update README.md in the same PR if your change affects setup, configuration, or behavior it describes.
- Be patient — this is maintained in spare time, so review may take a bit.

## Code of conduct

Be respectful and constructive. Disagreements about approach are fine and expected; personal attacks, harassment, or bad-faith behavior are not, and issues/PRs/comments that cross that line will be closed or removed.

## No financial contributions

This project does not want or accept donations, sponsorships, or any other form of financial support. If you'd like to give back, the most valuable thing you can do is contribute code, tests, docs, or a well-written bug report. Thank you!
