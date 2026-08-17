## What does this PR do?

A short description of the change and why it's needed. Link the issue it addresses, if any (`Closes #___`).

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactor / internal cleanup
- [ ] Other (describe above)

## How was this tested?

```bash
uv run ruff check .
uv run ty check .
uv run pytest tests/ -v
```

- Manually ran a real task and confirmed the change behaves as expected (see [CONTRIBUTING.md](../CONTRIBUTING.md#testing-your-change)):
- If this touches the sensitive-action gate or a browser tool: confirmed the approval prompt still triggers/skips correctly.

## Checklist

- [ ] I read [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] I updated README.md if this change affects setup, configuration, or documented behavior
- [ ] I did not commit any API keys, `.env` contents, or scraped/personal data
- [ ] This PR is focused on one change (not several unrelated things bundled together)
