"""The jdsl tool gateway — Tier A capture (design §8.1, §35 PR5).

The preferred capture mode: the model sees task tools *through* jdsl, so the
gateway records tool identity, schema, arguments, result, error, timing, and state
around mutations (§8.1). Wrapping a tool with the gateway records a canonical
tool.call.started/completed/failed triple on the sink, with the environment's
state snapshot attached around state-changing calls when an adapter is present.
"""

from __future__ import annotations

import time
from typing import Any

from jdsl.trace.events import EventKind, EventSource, TraceEvent
from jdsl.trace.sink import TraceSink
from jdsl_harness.state import EnvironmentAdapter


class ToolGateway:
    """Wraps callables/Tools so their calls are recorded to a trace sink. Preserves
    the original tool's schema and return value; capture is transparent to the
    caller (fail-open, §7.2 — a broken sink never breaks the tool call)."""

    def __init__(self, sink: TraceSink, *, capture_id: str, episode_id: str,
                 env: EnvironmentAdapter | None = None,
                 source: EventSource | None = None) -> None:
        self.sink = sink
        self.capture_id = capture_id
        self.episode_id = episode_id
        self.env = env
        self.source = source or EventSource(adapter="gateway")
        self._seq = 0

    def wrap(self, fn: Any, *, logical_id: str | None = None, host_name: str | None = None,
             destructive: bool = False) -> Any:
        """Return a callable that records each invocation. `logical_id` is the
        portable capability id; `destructive` triggers state snapshots (§8.1)."""
        name = host_name or getattr(fn, "name", None) or getattr(fn, "__name__", "tool")
        logical = logical_id or (self.env.canonical_tool(name) if self.env else name)

        def recorded(*args: Any, **kwargs: Any) -> Any:
            arguments = dict(kwargs)
            for i, a in enumerate(args):
                arguments[f"_arg{i}"] = a
            before = self._maybe_snapshot(destructive)
            started = self._emit(EventKind.TOOL_CALL_STARTED, actor="model", payload={
                "tool": {"logical_id": logical, "host_name": name}, "arguments": arguments,
            }, state_before=before)
            t0 = time.monotonic()
            try:
                result = fn(*args, **kwargs)
            except Exception as err:  # noqa: BLE001 — record then re-raise
                self._emit(EventKind.TOOL_CALL_FAILED, actor="tool",
                           parent_event_id=started.event_id, payload={
                               "tool": {"logical_id": logical, "host_name": name},
                               "error": str(err), "duration_ms": _ms(t0)})
                raise
            after = self._maybe_snapshot(destructive)
            kind = EventKind.TOOL_CALL_FAILED if _is_error(result) else EventKind.TOOL_CALL_COMPLETED
            self._emit(kind, actor="tool", parent_event_id=started.event_id, payload={
                "tool": {"logical_id": logical, "host_name": name},
                ("error" if kind == EventKind.TOOL_CALL_FAILED else "result"): result,
                "duration_ms": _ms(t0)}, state_after=after)
            return result

        recorded.logical_id = logical  # type: ignore[attr-defined]
        recorded.name = name  # type: ignore[attr-defined]
        return recorded

    def record_outcome(self) -> TraceEvent | None:
        """Emit the environment's task outcome, if the adapter reports one (§8.1)."""
        if self.env is None:
            return None
        outcome = self.env.outcome()
        if outcome is None:
            return None
        return self._emit(EventKind.ENVIRONMENT_VERDICT, actor="environment",
                          payload=outcome.to_payload())

    def _maybe_snapshot(self, destructive: bool) -> str | None:
        if not destructive or self.env is None:
            return None
        try:
            snap = self.env.snapshot()
        except Exception:  # noqa: BLE001
            return None
        return None if snap is None else str(snap)

    def _emit(self, kind: str, *, actor: str, payload: dict[str, Any],
              parent_event_id: str | None = None, state_before: str | None = None,
              state_after: str | None = None) -> TraceEvent:
        event = TraceEvent.new(kind, self.capture_id, self.episode_id, payload=payload,
                               actor=actor, source=self.source, parent_event_id=parent_event_id,
                               state_before_ref=state_before, state_after_ref=state_after)
        return self.sink.emit(event)


def _is_error(result: Any) -> bool:
    return str(result).strip().lower().startswith("error")


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


__all__ = ["ToolGateway"]
