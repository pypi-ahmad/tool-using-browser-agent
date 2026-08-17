# Disclaimer

Please read this before pointing the agent at a real website, account, or task.

## You run this entirely on your own machine, with your own credentials

Tool-Using Browser Agent is a local-first tool. There is no hosted version, no backend server operated by the author, and no account system. It runs a local browser (Playwright, headless Chromium) on your machine, and you supply your own API key for whichever cloud provider you configure (OpenAI or [Agnes AI](https://www.agnes-ai.com/en/docs/overview)).

## What actually leaves your machine

This is the part most disclaimers gloss over, so it's stated precisely:

- **Planning and reflection always use the cloud model** — every planning step sends your task description, the URLs of your open tabs, and a truncated summary (up to 500 characters per action, last 6 actions) of recent page content and extraction results to whichever cloud provider you've configured. This is not optional or occasional — it happens on every step of every run.
- **Only the actual click/fill/navigate execution first tries the local Ollama model.** If the local model can't produce a valid tool call, that instruction is escalated to the cloud model too.
- **Screenshots go to the cloud vision model** whenever the agent gets stuck (a selector fails, a cookie banner appears, a CAPTCHA blocks progress) — a full-page screenshot is sent for analysis.
- **Full extracted data content (the actual text/table/link content you pull from a page) is not sent to the cloud model** — only the truncated 500-character result summary in the action history is. The complete extracted records stay local, in your SQLite file.
- **Local Ollama is the only path that keeps browsing content off the network entirely** — this requires disabling cloud escalation, which the current UI does not offer as an on/off switch. If your task must never touch a cloud API, don't configure a cloud key at all; the app will fail at the planning step instead of silently using one.

## You are responsible for what you point this agent at

**You, and only you, are responsible for:**

- The websites you send this agent to, and complying with their terms of service. Automated browsing, clicking, and form-filling can violate a site's terms even when technically possible.
- Any account credentials, payment information, or personal data you let the agent interact with. The human-in-the-loop approval gate (triggered by keywords like "submit", "pay", "buy", "confirm", "purchase", "checkout", "place order") is a safety net, not a guarantee — review every approval prompt carefully before approving it.
- Deciding whether the task, page content, and screenshots involved may be sent to a third-party LLM provider. This includes anything visible on pages the agent navigates to, including logged-in account pages if you authorize the agent to interact with a session.
- Understanding and accepting your chosen provider's own data-handling, retention, and training-use policies.
- Any costs your provider charges for API usage. This project does not meter, cap, or reimburse API spend.
- Any consequences of actions the agent takes after you approve them — including submitted forms, made payments, or sent data.

## No warranty, no liability

This software is provided "as is," without warranty of any kind, as stated in the [MIT License](LICENSE). The author is not liable for any damage, data loss, unintended disclosure, unwanted purchases, API costs, account restrictions, or other consequences arising from your use of this tool. Use it at your own risk, and never leave it unattended on a task involving money or credentials.

## No financial support wanted

This project is free, open-source, and does not want or accept donations, sponsorships, or any other form of financial contribution — see [SUPPORT.md](SUPPORT.md).
