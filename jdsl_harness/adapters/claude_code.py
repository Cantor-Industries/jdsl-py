"""Claude Code host adapter (design §8.2, §29.1).

Translates Claude Code's structured hook payloads into canonical jdsl events. The
adapter uses only the structured JSON hook payload — never scraped terminal text
(§8.2). It is a pure function of the payload so it can be unit-tested against
recorded fixtures without running the host (§46 hook fixture tests).

Claude Code hook events used (§29.1): SessionStart, UserPromptSubmit, PreToolUse,
PostToolUse, PostToolUseFailure, SessionEnd. The tool call is correlated across
Pre/Post by (session, tool_name, tool_input).
"""

from __future__ import annotations

from typing import Any

from jdsl.trace.events import EventKind, EventSource, TraceEvent

HOST = "claude-code"
ADAPTER = "claude-hooks"

_SOURCE = EventSource(host=HOST, adapter=ADAPTER)


def to_events(payload: dict[str, Any], *, capture_id: str, model: str | None = None) -> list[TraceEvent]:
    """Map one Claude Code hook payload to zero or more canonical events. The
    session id becomes the episode id; unknown hook names are dropped (capture
    fidelity is recorded elsewhere, §8.2)."""
    hook = payload.get("hook_event_name") or payload.get("hook")
    episode_id = payload.get("session_id") or "ep_claude"
    src = EventSource(host=HOST, adapter=ADAPTER, model=model)

    def ev(kind: str, *, actor: str = "system", data: dict[str, Any] | None = None) -> TraceEvent:
        return TraceEvent.new(kind, capture_id, episode_id, payload=data or {}, actor=actor, source=src)

    if hook == "SessionStart":
        return [ev(EventKind.EPISODE_STARTED, data={"host": HOST})]
    if hook == "UserPromptSubmit":
        return [ev(EventKind.USER_MESSAGE, actor="user",
                   data={"text": payload.get("prompt") or payload.get("user_prompt", "")})]
    if hook == "PreToolUse":
        return [ev(EventKind.TOOL_CALL_STARTED, actor="model", data={
            "tool": {"host_name": payload.get("tool_name"), "logical_id": None},
            "arguments": payload.get("tool_input", {})})]
    if hook == "PostToolUse":
        response = payload.get("tool_response", payload.get("tool_result"))
        return [ev(EventKind.TOOL_CALL_COMPLETED, actor="tool", data={
            "tool": {"host_name": payload.get("tool_name")}, "result": response})]
    if hook in ("PostToolUseFailure", "PostToolBatchFailure"):
        return [ev(EventKind.TOOL_CALL_FAILED, actor="tool", data={
            "tool": {"host_name": payload.get("tool_name")},
            "error": payload.get("error") or payload.get("tool_response")})]
    if hook in ("SubagentStart", "SubagentStop"):
        kind = EventKind.HOST_SUBAGENT_STARTED if hook == "SubagentStart" else EventKind.HOST_SUBAGENT_FINISHED
        return [ev(kind, data={"agent": payload.get("subagent_type")})]
    if hook == "SessionEnd":
        return [ev(EventKind.EPISODE_FINISHED, data={"host": HOST})]
    return []


__all__ = ["to_events", "HOST", "ADAPTER"]
