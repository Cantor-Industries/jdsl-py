"""OpenCode host adapter.

The TypeScript plugin translates OpenCode hook inputs into the stable
``jdsl.opencode-hook.v1`` envelope. This module maps that envelope into canonical
jdsl trace events without depending on OpenCode's TypeScript types.
"""

from __future__ import annotations

from typing import Any

from jdsl.trace.events import EventKind, EventSource, TraceEvent
from jdsl_harness.adapters.correlation import ToolCallCorrelator, host_call_id

HOST = "opencode"
ADAPTER = "opencode-hooks"
SCHEMA = "jdsl.opencode-hook.v1"


class OpenCodeEnvelopeError(ValueError):
    """An OpenCode hook payload does not match the jdsl stable envelope."""


def to_events(payload: dict[str, Any], *, capture_id: str, model: str | None = None,
              correlator: ToolCallCorrelator | None = None) -> list[TraceEvent]:
    """Map one stable OpenCode envelope to canonical trace events."""
    _validate_envelope(payload)
    hook = payload["hook"]
    episode_id = str(payload.get("episode_id") or payload["session_id"])
    src = EventSource(host=HOST, adapter=ADAPTER, model=model)

    def ev(kind: str, *, actor: str = "system", data: dict[str, Any] | None = None) -> TraceEvent:
        return TraceEvent.new(kind, capture_id, episode_id, payload=data or {}, actor=actor, source=src)

    if hook == "session.created":
        return [ev(EventKind.EPISODE_STARTED, data={
            "host": HOST,
            "session_id": payload["session_id"],
            "directory": payload.get("directory"),
            "worktree": payload.get("worktree"),
        })]
    if hook == "tool.execute.before":
        event = ev(EventKind.TOOL_CALL_STARTED, actor="model", data={
            "tool": {"host_name": payload.get("tool"), "logical_id": None},
            "arguments": payload.get("args") or {},
            "directory": payload.get("directory"),
            "worktree": payload.get("worktree"),
        })
        cid = host_call_id(payload)
        if correlator is not None:
            event = correlator.started(event, host_call_id=cid, tool_name=payload.get("tool"))
        elif cid is not None:
            event.payload["host_call_id"] = cid
        return [event]
    if hook == "tool.execute.after":
        error = payload.get("error")
        kind = EventKind.TOOL_CALL_FAILED if error else EventKind.TOOL_CALL_COMPLETED
        body = {
            "tool": {"host_name": payload.get("tool")},
            "directory": payload.get("directory"),
            "worktree": payload.get("worktree"),
        }
        if error:
            body["error"] = str(error)
        else:
            body["result"] = payload.get("result")
        event = ev(kind, actor="tool", data=body)
        cid = host_call_id(payload)
        if correlator is not None:
            event = correlator.finished(event, host_call_id=cid, tool_name=payload.get("tool"))
        elif cid is not None:
            event.payload["host_call_id"] = cid
        return [event]
    if hook == "session.error":
        return [ev(EventKind.ANNOTATION, data={
            "host": HOST,
            "session_id": payload["session_id"],
            "kind": "session.error",
            "error": payload.get("error"),
        })]
    if hook in ("session.deleted", "session.finished", "session.ended"):
        return [ev(EventKind.EPISODE_FINISHED, data={"host": HOST, "session_id": payload["session_id"]})]
    if hook in ("session.idle", "session.updated", "session.status", "session.compacted"):
        return [ev(EventKind.ANNOTATION, data={
            "host": HOST,
            "session_id": payload["session_id"],
            "kind": hook,
            "status": payload.get("status"),
        })]
    return []


def _validate_envelope(payload: dict[str, Any]) -> None:
    if payload.get("schema") != SCHEMA:
        raise OpenCodeEnvelopeError(f"expected schema {SCHEMA!r}")
    if not isinstance(payload.get("hook"), str) or not payload["hook"]:
        raise OpenCodeEnvelopeError("missing hook")
    if not payload.get("session_id"):
        raise OpenCodeEnvelopeError("missing session_id")
    hook = payload["hook"]
    if hook.startswith("tool.execute."):
        if not payload.get("tool"):
            raise OpenCodeEnvelopeError("missing tool")
        if hook == "tool.execute.before" and "args" not in payload:
            raise OpenCodeEnvelopeError("missing args")
        if hook == "tool.execute.after" and "result" not in payload and "error" not in payload:
            raise OpenCodeEnvelopeError("missing result or error")


__all__ = ["to_events", "OpenCodeEnvelopeError", "HOST", "ADAPTER", "SCHEMA"]
