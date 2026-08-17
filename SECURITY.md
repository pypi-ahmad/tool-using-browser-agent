# Security Policy

## Supported versions

This project has no formal release line yet — security fixes apply to the current `main` branch.

## Reporting a vulnerability

Do not report vulnerabilities through public issues, discussions, pull requests, or social media.

Use GitHub's **Report a vulnerability** form under this repository's Security/Advisories tab to submit a private report. If that isn't available, open a minimal public issue asking for a private contact channel — do not include exploit details in that issue.

Include:

- A clear description of the vulnerability and affected code.
- Reproduction steps or a minimal proof of concept.
- Impact assessment and any suggested mitigation.

Do not include real API keys, browsing session data, or personal information in a report. The maintainer will acknowledge and investigate reports on a best-effort basis.

## Project security model

Tool-Using Browser Agent runs entirely locally: a headless Playwright browser, a local SQLite database (`agent_memory.db`), and calls to whichever LLM providers you configure (local Ollama, and a cloud provider for planning/reflection/vision — see [DISCLAIMER.md](DISCLAIMER.md) for exactly what that sends). It has no backend server, no accounts, and no telemetry.

- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `AGNES_API_KEY` are read only from the environment (`config.py`) and are never hardcoded, logged, or written to the SQLite store.
- Extracted data is written to a local SQLite file with no encryption at rest — treat `agent_memory.db` like any other file containing whatever you scraped.

## Known risks specific to an LLM-driven browser agent

This class of application has a real attack surface that a normal web app doesn't:

- **Prompt injection from page content.** The planner and actuator models read live page state (URLs, action results, and — via the vision fallback — full screenshots). A malicious or compromised page could include text designed to manipulate the model into taking an unintended action. The human-in-the-loop approval gate helps for anything matching its keyword list, but it is not a complete defense against this class of attack.
- **Keyword-based approval gate, not a semantic one.** `SENSITIVE_KEYWORDS` in `config.py` triggers approval on literal keyword matches ("submit", "pay", "buy", "confirm", "purchase", "checkout", "place order") in the planner's instruction text. An action that is sensitive but doesn't happen to contain one of these words, or is phrased differently by the model, will not pause for approval. Review the action log, not just the approval prompts.
- **No sandboxing beyond Playwright's own browser process and your OS user permissions.** The agent can navigate to any URL the model decides to visit and interact with any page it can reach — including sites you're already logged into in a way accessible to that browser profile (this app launches a fresh, isolated Playwright context by default, not your regular browser profile, but confirm this if you customize the launch).

## Safe operation

- Run this only on a trusted machine and user account.
- Never leave a run unattended on a task involving real payments, account changes, or credentials — approve/reject prompts require your judgment, not just a keyword match.
- Use the **Stop** button if the agent's actions look wrong, rather than waiting for it to self-correct.
- Treat `agent_memory.db` as containing whatever data you've had the agent extract — back it up, delete it, or exclude it from version control as appropriate for your use.
- Keep your Ollama server, Playwright/Chromium, and Python dependencies up to date.

## Not security vulnerabilities

The agent making a wrong click, choosing a bad selector, or failing to complete a task is a quality/reliability issue, not a security vulnerability, unless it demonstrates an actual trust-boundary bypass (e.g., executing an approved action's rejected variant, or leaking a credential into a log or the SQLite store). Report those separately as regular bugs.
