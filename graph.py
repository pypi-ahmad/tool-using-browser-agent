"""LangGraph state, nodes, and routing for the browser agent.

planner -> browser_actuator -> observer -> memory_updater -> persist_memory ->
reflector -> (planner | END). Human approval is added on top of this in a later
pass.
"""

from __future__ import annotations

import base64
from typing import Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, Field

from memory import mark_visited, trim_history
from persistence import save_record
from utils import bytes_to_b64, is_sensitive_text, utc_now_iso
from vision import analyze_screenshot

EXTRACTION_TOOLS = {"extract_text", "extract_table", "extract_links", "screenshot"}


class AgentState(TypedDict):
    task: str
    next_action: dict[str, Any] | None
    tabs: dict[str, str]
    active_tab: str | None
    action_history: list[dict]
    extracted_data: list[dict]
    persisted_count: int
    page_memory: dict[str, dict]
    last_observation: dict | None
    needs_vision: bool
    screenshot_b64: str | None
    step_count: int
    max_steps: int
    session_id: str
    status: Literal["running", "paused_for_approval", "done", "stopped", "error"]
    error: str | None


def build_initial_state(task: str, session_id: str, max_steps: int) -> AgentState:
    return AgentState(
        task=task,
        next_action=None,
        tabs={},
        active_tab=None,
        action_history=[],
        extracted_data=[],
        persisted_count=0,
        page_memory={},
        last_observation=None,
        needs_vision=False,
        screenshot_b64=None,
        step_count=0,
        max_steps=max_steps,
        session_id=session_id,
        status="running",
        error=None,
    )


class PlannerDecision(BaseModel):
    instruction: str = Field(
        description="One concrete next browser action in plain language, e.g. "
        "'navigate to https://example.com' or 'click the Add to Cart button'."
    )
    sensitive: bool = Field(
        description="True if this action submits a form, makes a payment, or "
        "otherwise commits something irreversible."
    )
    reasoning: str = Field(description="Brief reasoning for this step.")


class ReflectorDecision(BaseModel):
    finished: bool = Field(
        description="True if the task is complete or cannot proceed further."
    )
    reasoning: str = Field(description="Brief reasoning for continuing or finishing.")


def _recent_history_text(state: AgentState, limit: int = 6) -> str:
    entries = state["action_history"][-limit:]
    if not entries:
        return "(no actions yet)"
    lines = []
    for e in entries:
        line = f"- {e['instruction']} -> tool={e['tool']} result={e['result_summary']!r} error={e.get('error')}"
        if e.get("vision_guidance"):
            line += f"\n  vision guidance: {e['vision_guidance']}"
        lines.append(line)
    return "\n".join(lines)


async def planner_node(state: AgentState, config: RunnableConfig) -> dict:
    llm = config["configurable"]["planner_llm"]
    session = config["configurable"]["browser_session"]
    # Read tabs live from the session rather than state["tabs"]: state only gets
    # synced after browser_actuator runs once, so on the very first planner call
    # of a run (or right after a fresh open_new_tab) state["tabs"] would lag
    # behind whatever page is actually already open.
    tabs = session.list_tabs()
    active_url = tabs.get(session.active_tab) if session.active_tab else None
    structured = llm.with_structured_output(PlannerDecision)
    prompt = (
        f"Task: {state['task']}\n"
        f"Open tabs: {tabs or '(none yet)'}\n"
        f"Currently viewing: {active_url or '(no page open yet)'}\n"
        f"Recent actions:\n{_recent_history_text(state)}\n\n"
        "Decide the single next concrete browser action needed to make progress on "
        "the task. If no page is open yet, the first action must be a navigate to a "
        "specific URL. If the task involves multiple sites (e.g. comparing prices "
        "across sites), open a separate tab per site with open_new_tab instead of "
        "reusing one tab, and use switch_tab to move between them; refer to a "
        "specific tab_id when acting on a tab that isn't the current one."
    )
    decision: PlannerDecision = await structured.ainvoke(
        [
            SystemMessage("You plan browser-automation steps one at a time."),
            HumanMessage(prompt),
        ]
    )
    sensitive = decision.sensitive or is_sensitive_text(decision.instruction)
    return {
        "next_action": {
            "instruction": decision.instruction,
            "sensitive": sensitive,
            "reasoning": decision.reasoning,
        }
    }


def route_after_planner(
    state: AgentState,
) -> Literal["human_approval", "browser_actuator"]:
    action = state["next_action"]
    return (
        "human_approval" if action and action.get("sensitive") else "browser_actuator"
    )


async def human_approval_node(state: AgentState, config: RunnableConfig) -> dict:
    action = state["next_action"]
    decision = interrupt(
        {
            "type": "approval_required",
            "instruction": action["instruction"],
            "reasoning": action.get("reasoning"),
        }
    )
    approved = decision == "approve" or (
        isinstance(decision, dict) and decision.get("approved")
    )
    if approved:
        return {}
    return {
        "next_action": None,
        "step_count": state["step_count"] + 1,
        "last_observation": {
            "instruction": action["instruction"],
            "tool": None,
            "result_summary": "",
            "error": "action rejected by human approval",
        },
    }


def route_after_approval(state: AgentState) -> Literal["browser_actuator", "observer"]:
    return "browser_actuator" if state["next_action"] is not None else "observer"


async def browser_actuator_node(state: AgentState, config: RunnableConfig) -> dict:
    session = config["configurable"]["browser_session"]
    tools_by_name = config["configurable"]["tools_by_name"]
    local_llm = config["configurable"]["local_llm"]
    planner_llm = config["configurable"]["planner_llm"]
    instruction = state["next_action"]["instruction"]

    system = SystemMessage(
        "You control a web browser via tools. Given the instruction, call exactly "
        "one tool that carries it out."
    )
    messages = [system, HumanMessage(instruction)]

    response = await local_llm.bind_tools(list(tools_by_name.values())).ainvoke(
        messages
    )
    escalated = False
    if not response.tool_calls:
        response = await planner_llm.bind_tools(list(tools_by_name.values())).ainvoke(
            messages
        )
        escalated = True

    result_summary: str
    error: str | None = None
    tool_name = None

    if not response.tool_calls:
        tool_name = None
        error = "no tool call produced (local model, then GPT escalation, both failed)"
        result_summary = ""
    else:
        call = response.tool_calls[0]
        tool_name = call["name"]
        tool = tools_by_name.get(tool_name)
        if tool is None:
            error = f"unknown tool: {tool_name!r}"
            result_summary = ""
        else:
            try:
                result = await tool.ainvoke(call["args"])
                result_summary = str(result)[:500]
            except (PlaywrightError, ValueError) as exc:
                error = str(exc)
                result_summary = ""

    needs_vision = error is not None
    screenshot_b64 = state["screenshot_b64"]
    if needs_vision and session.active_tab is not None:
        try:
            screenshot_b64 = bytes_to_b64(await session.screenshot())
        except PlaywrightError:
            pass

    return {
        "tabs": session.list_tabs(),
        "active_tab": session.active_tab,
        "step_count": state["step_count"] + 1,
        "needs_vision": needs_vision,
        "screenshot_b64": screenshot_b64,
        "last_observation": {
            "instruction": instruction,
            "tool": tool_name,
            "result_summary": result_summary,
            "error": error,
            "escalated_to_gpt": escalated,
        },
    }


async def observer_node(state: AgentState, config: RunnableConfig) -> dict:
    session = config["configurable"]["browser_session"]
    url = None
    if session.active_tab is not None:
        url = session.pages[session.active_tab].url
    observation = dict(state["last_observation"] or {})
    observation["url"] = url

    if state["needs_vision"] and state["screenshot_b64"]:
        vision_llm = config["configurable"].get("vision_llm")
        if vision_llm is not None:
            guidance = await analyze_screenshot(
                vision_llm,
                base64.b64decode(state["screenshot_b64"]),
                observation.get("instruction", ""),
                state["task"],
            )
            observation["vision_guidance"] = guidance

    return {"last_observation": observation, "needs_vision": False}


async def memory_updater_node(state: AgentState, config: RunnableConfig) -> dict:
    obs = state["last_observation"] or {}
    now = utc_now_iso()

    history_entry = {
        "step": state["step_count"],
        "instruction": obs.get("instruction"),
        "tool": obs.get("tool"),
        "result_summary": obs.get("result_summary"),
        "error": obs.get("error"),
        "vision_guidance": obs.get("vision_guidance"),
        "timestamp": now,
    }
    action_history = trim_history([*state["action_history"], history_entry])

    extracted_data = state["extracted_data"]
    if obs.get("tool") in EXTRACTION_TOOLS and not obs.get("error"):
        extracted_data = [
            *extracted_data,
            {
                "type": obs["tool"],
                "url": obs.get("url"),
                "data": obs.get("result_summary"),
                "timestamp": now,
            },
        ]

    page_memory = state["page_memory"]
    if obs.get("url"):
        page_memory = mark_visited(page_memory, obs["url"], now)

    return {
        "action_history": action_history,
        "extracted_data": extracted_data,
        "page_memory": page_memory,
    }


async def persist_memory_node(state: AgentState, config: RunnableConfig) -> dict:
    """Write any extracted_data records added since the last pass to SQLite.

    Runs every pass (not just at the end) so a Stop mid-run doesn't lose
    already-extracted data.
    """
    db_path = config["configurable"].get("memory_db_path")
    new_records = state["extracted_data"][state["persisted_count"] :]
    for record in new_records:
        kwargs = {"db_path": db_path} if db_path else {}
        save_record(
            {
                "session_id": state["session_id"],
                "task": state["task"],
                "url": record.get("url"),
                "type": record.get("type"),
                "data": record.get("data"),
                "created_at": record.get("timestamp", utc_now_iso()),
            },
            **kwargs,
        )
    return {"persisted_count": len(state["extracted_data"])}


async def reflector_node(state: AgentState, config: RunnableConfig) -> dict:
    if state["step_count"] >= state["max_steps"]:
        return {"status": "done", "error": state["error"]}

    llm = config["configurable"]["planner_llm"]
    structured = llm.with_structured_output(ReflectorDecision)
    prompt = (
        f"Task: {state['task']}\n"
        f"Steps taken: {state['step_count']}/{state['max_steps']}\n"
        f"Recent actions:\n{_recent_history_text(state)}\n"
        f"Extracted data so far: {len(state['extracted_data'])} record(s)\n\n"
        "Is the task finished, or should the agent continue?"
    )
    decision: ReflectorDecision = await structured.ainvoke(
        [
            SystemMessage("You judge whether a browser-automation task is complete."),
            HumanMessage(prompt),
        ]
    )
    return {"status": "done" if decision.finished else "running"}


def route_after_reflector(state: AgentState) -> Literal["planner", "__end__"]:
    return END if state["status"] == "done" else "planner"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("browser_actuator", browser_actuator_node)
    graph.add_node("observer", observer_node)
    graph.add_node("memory_updater", memory_updater_node)
    graph.add_node("persist_memory", persist_memory_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("reflector", reflector_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner", route_after_planner, ["human_approval", "browser_actuator"]
    )
    graph.add_conditional_edges(
        "human_approval", route_after_approval, ["browser_actuator", "observer"]
    )
    graph.add_edge("browser_actuator", "observer")
    graph.add_edge("observer", "memory_updater")
    graph.add_edge("memory_updater", "persist_memory")
    graph.add_edge("persist_memory", "reflector")
    graph.add_conditional_edges("reflector", route_after_reflector, ["planner", END])

    return graph.compile(checkpointer=InMemorySaver())
