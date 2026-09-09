"""Gemini CLI host adapter (design §8.2, §29.2).

Maps Gemini CLI's hook payloads to canonical jdsl events. Gemini exposes a broader
surface than Claude Code, including model and tool-selection events (§29.2); for
the first release these are used for capture only (not enforcement). Full model
requests are not stored by default (§29.2).

Hooks used: SessionStart, BeforeAgent, BeforeToolSelection, BeforeTool, AfterTool,
AfterAgent, SessionEnd.
"""

from __future__ import annotations

from typing import Any

from jdsl.trace.events import EventKind, EventSource, TraceEvent
from jdsl_harness.adapters.correlation import ToolCallCorrelator, host_call_id

HOST = "gemini-cli"
ADAPTER = "gemini-hooks"


def to_events(payload: dict[str, Any], *, capture_id: str, model: str | None = None,
              correlator: ToolCallCorrelator | None = None) -> list[TraceEvent]:
    hook = payload.get("hook") or payload.get("event")
    episode_id = payload.get("session_id") or payload.get("sessionId") or "ep_gemini"
    src = EventSource(host=HOST, adapter=ADAPTER, model=model)

    def ev(kind: str, *, actor: str = "system", data: dict[str, Any] | None = None) -> TraceEvent:
        return TraceEvent.new(kind, capture_id, episode_id, payload=data or {}, actor=actor, source=src)

    if hook in ("SessionStart", "BeforeAgent"):
        return [ev(EventKind.EPISODE_STARTED, data={"host": HOST})] if hook == "SessionStart" else []
    if hook == "BeforeToolSelection":
        tools = payload.get("available_tools") or payload.get("tools") or []
        return [ev(EventKind.TOOLSET_EXPOSED, data={
            "tools": [{"host_name": t if isinstance(t, str) else t.get("name")} for t in tools]})]
    if hook == "BeforeTool":
        tool = payload.get("tool_name") or payload.get("name")
        event = ev(EventKind.TOOL_CALL_STARTED, actor="model", data={
            "tool": {"host_name": payload.get("tool_name") or payload.get("name")},
            "arguments": payload.get("args") or payload.get("tool_input", {})})
        cid = host_call_id(payload)
        if correlator is not None:
            event = correlator.started(event, host_call_id=cid, tool_name=tool)
        elif cid is not None:
            event.payload["host_call_id"] = cid
        return [event]
    if hook == "AfterTool":
        tool = payload.get("tool_name") or payload.get("name")
        cid = host_call_id(payload)
        error = payload.get("error")
        if error:
            event = ev(EventKind.TOOL_CALL_FAILED, actor="tool", data={
                "tool": {"host_name": tool}, "error": error})
        else:
            event = ev(EventKind.TOOL_CALL_COMPLETED, actor="tool", data={
                "tool": {"host_name": tool},
                "result": payload.get("result") or payload.get("output")})
        if correlator is not None:
            event = correlator.finished(event, host_call_id=cid, tool_name=tool)
        elif cid is not None:
            event.payload["host_call_id"] = cid
        return [event]
    if hook in ("SessionEnd", "AfterAgent"):
        return [ev(EventKind.EPISODE_FINISHED, data={"host": HOST})] if hook == "SessionEnd" else []
    return []


__all__ = ["to_events", "HOST", "ADAPTER"]
