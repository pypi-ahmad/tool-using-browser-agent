"""Pure conditional-edge / short-circuit logic. No LLM, no network, no browser."""

import pytest
from langgraph.graph import END

from graph import (
    build_initial_state,
    reflector_node,
    route_after_approval,
    route_after_planner,
    route_after_reflector,
)


def test_route_after_reflector_done_goes_to_end():
    state = build_initial_state("task", "session-1", max_steps=10)
    state["status"] = "done"
    assert route_after_reflector(state) == END


def test_route_after_reflector_running_goes_to_planner():
    state = build_initial_state("task", "session-1", max_steps=10)
    state["status"] = "running"
    assert route_after_reflector(state) == "planner"


def test_route_after_planner_sensitive_goes_to_approval():
    state = build_initial_state("task", "session-1", max_steps=10)
    state["next_action"] = {
        "instruction": "click Buy Now",
        "sensitive": True,
        "reasoning": "r",
    }
    assert route_after_planner(state) == "human_approval"


def test_route_after_planner_non_sensitive_goes_to_actuator():
    state = build_initial_state("task", "session-1", max_steps=10)
    state["next_action"] = {
        "instruction": "navigate to example.com",
        "sensitive": False,
        "reasoning": "r",
    }
    assert route_after_planner(state) == "browser_actuator"


def test_route_after_approval_rejected_skips_actuator():
    state = build_initial_state("task", "session-1", max_steps=10)
    state["next_action"] = None  # human_approval_node clears this on rejection
    assert route_after_approval(state) == "observer"


def test_route_after_approval_approved_goes_to_actuator():
    state = build_initial_state("task", "session-1", max_steps=10)
    state["next_action"] = {
        "instruction": "click Buy Now",
        "sensitive": True,
        "reasoning": "r",
    }
    assert route_after_approval(state) == "browser_actuator"


class _PoisonLLM:
    """Raises if actually invoked — proves the max-steps short-circuit skips the LLM."""

    def with_structured_output(self, *_args, **_kwargs):
        raise AssertionError(
            "reflector_node should not call the LLM once max_steps is reached"
        )


@pytest.mark.asyncio
async def test_reflector_forces_finish_at_max_steps_without_calling_llm():
    state = build_initial_state("task", "session-1", max_steps=3)
    state["step_count"] = 3
    config = {"configurable": {"planner_llm": _PoisonLLM()}}

    result = await reflector_node(state, config)

    assert result["status"] == "done"


@pytest.mark.asyncio
async def test_reflector_continues_below_max_steps_would_call_llm():
    state = build_initial_state("task", "session-1", max_steps=10)
    state["step_count"] = 1
    config = {"configurable": {"planner_llm": _PoisonLLM()}}

    with pytest.raises(AssertionError):
        await reflector_node(state, config)
