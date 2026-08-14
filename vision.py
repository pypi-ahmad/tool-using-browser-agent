"""Screenshot understanding via GPT vision. Only called when needs_vision is set
(a selector failed, or the page looks broken/blocked, e.g. a cookie banner or
anti-bot challenge) — not on every step.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from utils import bytes_to_b64


async def analyze_screenshot(
    vision_llm: BaseChatModel, screenshot_bytes: bytes, instruction: str, task: str
) -> str:
    """Ask the vision model what to do next, given a failed action and a screenshot.

    Returns plain language the planner/actuator can act on next turn (e.g. the exact
    visible text of the element to click, or why the page looks blocked). Degrades to
    a short note instead of raising if the call fails — the configured GPT model
    might not be vision-capable, and vision is a best-effort fallback, not a hard
    dependency for the rest of the graph to keep running.
    """
    b64 = bytes_to_b64(screenshot_bytes)
    message = HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    f"Task: {task}\n"
                    f"The last attempted action was: {instruction!r}, but it failed "
                    "(selector not found, timed out, or the page didn't respond as "
                    "expected).\n"
                    "Look at this screenshot and describe what should be clicked or "
                    "filled next, in plain language (e.g. the exact visible text of "
                    "a button/link), or explain why the page looks blocked (cookie "
                    "banner, login wall, CAPTCHA, etc.)."
                ),
            },
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]
    )
    try:
        response = await vision_llm.ainvoke(
            [
                SystemMessage(
                    "You analyze browser screenshots to unblock a stuck automation agent."
                ),
                message,
            ]
        )
        return (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )
    except Exception as exc:  # noqa: BLE001 - best-effort fallback, must not crash the graph
        return f"(vision analysis unavailable: {exc})"
