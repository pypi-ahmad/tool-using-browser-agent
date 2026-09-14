# Contributing

Guidelines for development and code contributions to the tool-using browser agent repository.

## Development environment setup

1. Clone the repository and navigate to the project directory:
   ```bash
   git clone https://github.com/pypi-ahmad/tool-using-browser-agent.git
   cd tool-using-browser-agent
   ```
2. Install Python dependencies:
   ```bash
   uv sync --all-groups
   ```
3. Install Playwright browser binaries:
   ```bash
   uv run playwright install chromium
   ```
4. Configure environment variables:
   ```bash
   cp .env.example .env
   ```
   Add required API credentials (`OPENAI_API_KEY` or `AGNES_API_KEY`) and verify that Ollama is accessible at `http://localhost:11434`.

## Quality checks

Development tools are defined in `pyproject.toml` under the `dev` dependency group.

### Linter

Run Ruff over the codebase:

```bash
uv run ruff check .
```

### Type checker

Run ty to perform static type analysis:

```bash
uv run ty check .
```

*Note on current diagnostics:* As of this documentation, running `uv run ty check .` reports 8 type diagnostics in `graph.py`, `persistence.py`, and `tools/browser_tools.py`.

### Test runner

Run pytest:

```bash
uv run pytest
```

*Note on test execution:* The test suite in `tests/` contains 15 automated unit tests (`test_browser_tools.py`, `test_graph_routing.py`, `test_persistence.py`). All tests should pass before submitting code changes.

## Branch and integration expectations

- **Continuous integration:** The repository does not currently contain continuous integration configurations (no `.github/workflows/` files exist).
- **Branch naming and policies:** No branch conventions or merge requirements are codified in repository scripts.
- **Pull request process:** Issue and pull request templates are available under `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE.md`.
