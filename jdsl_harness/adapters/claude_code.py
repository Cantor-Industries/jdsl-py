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

import json
from typing import Any

from jdsl.trace.events import EventKind, EventSource, TraceEvent
from jdsl_harness.adapters.correlation import ToolCallCorrelator, host_call_id

HOST = "claude-code"
ADAPTER = "claude-hooks"

_SOURCE = EventSource(host=HOST, adapter=ADAPTER)


def to_events(payload: dict[str, Any], *, capture_id: str, model: str | None = None,
              correlator: ToolCallCorrelator | None = None) -> list[TraceEvent]:
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
        event = ev(EventKind.TOOL_CALL_STARTED, actor="model", data={
            "tool": {"host_name": payload.get("tool_name"), "logical_id": None},
            "arguments": payload.get("tool_input", {})})
        cid = host_call_id(payload)
        if correlator is not None:
            event = correlator.started(event, host_call_id=cid, tool_name=payload.get("tool_name"))
        elif cid is not None:
            event.payload["host_call_id"] = cid
        return [event]
    if hook == "PostToolUse":
        response = payload.get("tool_response", payload.get("tool_result"))
        event = ev(EventKind.TOOL_CALL_COMPLETED, actor="tool", data={
            "tool": {"host_name": payload.get("tool_name")},
            "result": _normalize_result(response)})
        cid = host_call_id(payload)
        if correlator is not None:
            event = correlator.finished(event, host_call_id=cid, tool_name=payload.get("tool_name"))
        elif cid is not None:
            event.payload["host_call_id"] = cid
        return [event]
    if hook in ("PostToolUseFailure", "PostToolBatchFailure"):
        event = ev(EventKind.TOOL_CALL_FAILED, actor="tool", data={
            "tool": {"host_name": payload.get("tool_name")},
            "error": payload.get("error") or payload.get("tool_response")})
        cid = host_call_id(payload)
        if correlator is not None:
            event = correlator.finished(event, host_call_id=cid, tool_name=payload.get("tool_name"))
        elif cid is not None:
            event.payload["host_call_id"] = cid
        return [event]
    if hook in ("SubagentStart", "SubagentStop"):
        kind = EventKind.HOST_SUBAGENT_STARTED if hook == "SubagentStart" else EventKind.HOST_SUBAGENT_FINISHED
        return [ev(kind, data={"agent": payload.get("subagent_type")})]
    if hook == "SessionEnd":
        return [ev(EventKind.EPISODE_FINISHED, data={"host": HOST})]
    return []


def _normalize_result(result: Any) -> Any:
    """Recover structured content from an MCP-style tool response so exact-dataflow
    lineage (§16.1) can see discrete identifier values instead of a JSON blob.

    Claude Code may deliver an MCP tool result to the PostToolUse hook wrapped as a
    content envelope (``{"content": [{"type": "text", "text": "<json>"}]}``), as a
    bare content-block list (``[{"type": "text", "text": "<json>"}]``, the shape a
    single-object MCP tool return arrives in), as an MCP ``structuredContent``
    object, or as a bare JSON string. Any one structured
    payload is unwrapped from those shapes; already-structured or plain-text results
    pass through unchanged (a text blob never starts with ``{``/``[`` so it is left
    alone — no false parsing of Read/Bash output)."""
    unwrapped = _unwrap_content(result)
    return unwrapped if unwrapped is not None else result


def _unwrap_content(result: Any) -> Any:
    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if isinstance(structured, (dict, list)):
            # MCP wraps a non-object tool return as {"result": <value>}
            if isinstance(structured, dict) and set(structured) == {"result"}:
                return structured["result"]
            return structured
        if isinstance(result.get("content"), list):
            return _parse_blocks(result["content"])
    if isinstance(result, list):
        # A bare content-block list, e.g. Claude Code delivers a single-object MCP
        # return as [{"type": "text", "text": "<json>"}] with no wrapper dict.
        return _parse_blocks(result)
    if isinstance(result, str):
        return _maybe_json(result)
    return None


def _parse_blocks(blocks: list) -> Any:
    """Parse the JSON text carried by a list of MCP ``{"type": "text", ...}`` content
    blocks. Returns the single decoded value, a list of them, or None if none parse."""
    parsed = [_maybe_json(b.get("text")) for b in blocks
              if isinstance(b, dict) and b.get("type") == "text"]
    parsed = [p for p in parsed if p is not None]
    if len(parsed) == 1:
        return parsed[0]
    if parsed:
        return parsed
    return None


def _maybe_json(text: Any) -> Any:
    """Parse a string only if it is clearly a JSON object/array; else None."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped)
    except ValueError:
        return None


__all__ = ["to_events", "HOST", "ADAPTER"]
