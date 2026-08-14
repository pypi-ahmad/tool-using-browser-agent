"""Streamlit frontend: task input, live agent view, human-approval prompts,
persistent memory browser, and result downloads.

Run with: streamlit run app.py

Workers (AgentRunner._run) must never call st.* — Streamlit APIs only work on the
main script thread. The agent runs in its own daemon thread with its own asyncio
event loop (Playwright async requires the same loop for the life of the browser),
and the UI polls a lock-guarded snapshot. Pattern based on the background-job
registry in D:\\AI\\Github\\local-ai-chat-studio\\src\\jobs.py, adapted from
sync-streaming-to-a-registry to async-graph-to-a-snapshot.
"""

from __future__ import annotations

import asyncio
import threading
import uuid

import streamlit as st
from langgraph.types import Command

from config import (
    CLOUD_PROVIDER_CHOICES,
    LOCAL_MODEL_CHOICES,
    MEMORY_DB_PATH,
    Settings,
    get_local_llm,
    get_planner_llm,
    get_vision_llm,
)
from graph import build_graph, build_initial_state
from memory import to_csv_bytes, to_json
from persistence import list_recent, search_memory
from tools.browser_tools import BrowserSession, build_tools

LIVE_STATUSES = {"running", "paused_for_approval"}
TERMINAL_STATUSES = {"done", "stopped", "error"}


class AgentRunner:
    """One agent run: owns its browser/event-loop thread, exposes a lock-guarded
    snapshot for the UI to poll, and a small control surface (stop, approve)."""

    def __init__(
        self, task: str, local_model: str, cloud_provider: str, max_steps: int
    ) -> None:
        self.task = task
        self.local_model = local_model
        self.cloud_provider = cloud_provider
        self.max_steps = max_steps
        self.session_id = uuid.uuid4().hex[:8]

        self._lock = threading.Lock()
        self._approval_event = threading.Event()
        self.status = "running"
        self.action_log: list[dict] = []
        self.tabs: dict[str, str] = {}
        self.extracted_data: list[dict] = []
        self.screenshot_b64: str | None = None
        self.error: str | None = None
        self.pending_approval: dict | None = None
        self._resume_decision: str | None = None
        self._stop_requested = False

        self._thread = threading.Thread(target=self._run_in_thread, daemon=True)
        self._thread.start()

    def request_stop(self) -> None:
        with self._lock:
            self._stop_requested = True

    def submit_approval(self, decision: str) -> None:
        with self._lock:
            self._resume_decision = decision
            self.pending_approval = None
        self._approval_event.set()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "action_log": list(self.action_log),
                "tabs": dict(self.tabs),
                "extracted_data": list(self.extracted_data),
                "screenshot_b64": self.screenshot_b64,
                "error": self.error,
                "pending_approval": self.pending_approval,
            }

    def _run_in_thread(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_async())
        finally:
            loop.close()

    async def _run_async(self) -> None:
        settings = Settings(cloud_provider=self.cloud_provider)
        session = BrowserSession(headless=True)
        try:
            await session.start()
            tools_by_name = {t.name: t for t in build_tools(session)}
            graph = build_graph()
            graph_input = build_initial_state(
                self.task, self.session_id, self.max_steps
            )
            config = {
                "configurable": {
                    "thread_id": self.session_id,
                    "memory_db_path": MEMORY_DB_PATH,
                    "browser_session": session,
                    "tools_by_name": tools_by_name,
                    "planner_llm": get_planner_llm(settings),
                    "local_llm": get_local_llm(settings, self.local_model),
                    "vision_llm": get_vision_llm(settings),
                }
            }

            last_known_status = "done"
            while True:
                with self._lock:
                    if self._stop_requested:
                        self.status = "stopped"
                        return

                interrupt_payload = None
                # stream_mode="updates" yields {node_name: partial_state} after each
                # node finishes, so the UI updates step by step instead of only once
                # the whole multi-step task (which may take many planner/actuator
                # cycles) finally reaches END or an interrupt.
                async for chunk in graph.astream(
                    graph_input, config, stream_mode="updates"
                ):
                    with self._lock:
                        if self._stop_requested:
                            self.status = "stopped"
                            return
                    if "__interrupt__" in chunk:
                        interrupt_payload = chunk["__interrupt__"][0].value
                        break
                    for update in chunk.values():
                        with self._lock:
                            if "tabs" in update:
                                self.tabs = update["tabs"]
                            if update.get("screenshot_b64"):
                                self.screenshot_b64 = update["screenshot_b64"]
                            if "action_history" in update:
                                self.action_log = update["action_history"]
                            if "extracted_data" in update:
                                self.extracted_data = update["extracted_data"]
                            if update.get("error"):
                                self.error = update["error"]
                            if "status" in update:
                                last_known_status = update["status"]

                if interrupt_payload is not None:
                    with self._lock:
                        self.pending_approval = interrupt_payload
                        self.status = "paused_for_approval"
                    self._approval_event.wait()
                    self._approval_event.clear()
                    with self._lock:
                        if self._stop_requested:
                            self.status = "stopped"
                            return
                        decision = self._resume_decision
                        self.status = "running"
                    graph_input = Command(resume=decision)
                    continue

                with self._lock:
                    self.status = last_known_status
                return
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI; the worker thread must not crash silently
            with self._lock:
                self.error = str(exc)
                self.status = "error"
        finally:
            await session.close()


def _is_live(status: str | None) -> bool:
    return status in LIVE_STATUSES


st.set_page_config(page_title="Tool-Using Browser Agent", layout="wide")
st.title("Tool-Using Browser Agent")

if "runner" not in st.session_state:
    st.session_state.runner = None

runner: AgentRunner | None = st.session_state.runner
current_status = runner.snapshot()["status"] if runner else None

with st.form("task_form"):
    task = st.text_area(
        "Task",
        placeholder="Compare iPhone 16 prices on Amazon and Flipkart",
        height=80,
        disabled=_is_live(current_status),
    )
    col_model, col_cloud, col_steps = st.columns([2, 1, 1])
    with col_model:
        local_model = st.selectbox("Local model (Ollama)", LOCAL_MODEL_CHOICES, index=0)
    with col_cloud:
        cloud_provider = st.selectbox(
            "Cloud model (planning/vision)", CLOUD_PROVIDER_CHOICES, index=0
        )
    with col_steps:
        max_steps = st.number_input("Max steps", min_value=1, max_value=100, value=25)
    start_clicked = st.form_submit_button(
        "Start", disabled=_is_live(current_status), type="primary"
    )

if start_clicked and task.strip():
    st.session_state.runner = AgentRunner(
        task=task.strip(),
        local_model=local_model,
        cloud_provider=cloud_provider,
        max_steps=int(max_steps),
    )
    st.rerun()

if runner is not None and st.button("Stop", disabled=not _is_live(current_status)):
    runner.request_stop()

run_every = "1s" if _is_live(current_status) else None


@st.fragment(run_every=run_every)
def live_view() -> None:
    live_runner: AgentRunner | None = st.session_state.runner
    if live_runner is None:
        return
    snap = live_runner.snapshot()
    was_live = _is_live(current_status)

    st.subheader(f"Status: {snap['status']}")

    if snap["pending_approval"]:
        approval = snap["pending_approval"]
        st.warning(
            f"Approval needed: **{approval.get('instruction')}**\n\n"
            f"Reasoning: {approval.get('reasoning') or '(none given)'}"
        )
        col_approve, col_reject = st.columns(2)
        if col_approve.button("Approve", key="approve_btn"):
            live_runner.submit_approval("approve")
            st.rerun()
        if col_reject.button("Reject", key="reject_btn"):
            live_runner.submit_approval("reject")
            st.rerun()

    if snap["error"]:
        st.error(snap["error"])

    col_log, col_side = st.columns([2, 1])
    with col_log:
        st.markdown("**Action log**")
        if snap["action_log"]:
            for entry in reversed(snap["action_log"]):
                marker = "✅" if not entry.get("error") else "❌"
                st.text(
                    f"{marker} step {entry.get('step')}: {entry.get('instruction')}"
                )
                if entry.get("error"):
                    st.caption(f"error: {entry['error']}")
        else:
            st.caption("(no actions yet)")

    with col_side:
        st.markdown("**Open tabs**")
        if snap["tabs"]:
            for tab_id, url in snap["tabs"].items():
                st.caption(f"{tab_id}: {url}")
        else:
            st.caption("(none yet)")

        if snap["screenshot_b64"]:
            st.markdown("**Latest screenshot**")
            st.image(f"data:image/png;base64,{snap['screenshot_b64']}")

    st.markdown("**Extracted data**")
    if snap["extracted_data"]:
        st.dataframe(snap["extracted_data"], width="stretch")
    else:
        st.caption("(none yet)")

    if not was_live and run_every is not None:
        # Status just transitioned to terminal mid-poll: force one full rerun so
        # the outer script recomputes run_every=None and the interval stops.
        st.rerun()


if runner is not None:
    live_view()

final_snapshot = runner.snapshot() if runner else None
if (
    final_snapshot
    and final_snapshot["status"] in TERMINAL_STATUSES
    and final_snapshot["extracted_data"]
):
    st.subheader("Final results")
    records = final_snapshot["extracted_data"]
    st.download_button(
        "Download JSON", to_json(records), file_name="extracted_data.json"
    )
    st.download_button(
        "Download CSV", to_csv_bytes(records), file_name="extracted_data.csv"
    )

st.divider()
with st.expander("Persistent memory browser"):
    query = st.text_input("Search past sessions (matches URL, task, or extracted data)")
    records = search_memory(query, limit=50) if query.strip() else list_recent(limit=50)
    if records:
        st.dataframe(records, width="stretch")
    else:
        st.caption("(no persisted records yet)")
