"""Tool-call correlation for host hooks.

Host integrations often deliver "before tool" and "after tool" as separate HTTP
posts. This small state object remembers started calls by host-provided call id
and annotates completion events with the correct ``parent_event_id`` so replay and
normalization do not have to guess from sequence order.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from jdsl.trace.events import TraceEvent


@dataclass
class ToolCallCorrelator:
    """Short-lived in-memory correlation state scoped to one ingest process."""
    _by_id: dict[tuple[str, str, str], str] = field(default_factory=dict)
    _open: dict[tuple[str, str], list[tuple[str, str, str | None]]] = field(default_factory=dict)
    _counter: Any = field(default_factory=lambda: itertools.count(1))

    def started(self, event: TraceEvent, *, host_call_id: str | None,
                tool_name: str | None = None) -> TraceEvent:
        cid = host_call_id or f"adapter-local-{next(self._counter)}"
        event.payload["host_call_id"] = cid
        event.payload["correlation"] = {
            "method": "host_call_id" if host_call_id else "adapter_local",
            "fidelity": "exact" if host_call_id else "inferred",
        }
        key = (event.capture_id, event.episode_id, cid)
        self._by_id[key] = event.event_id
        self._open.setdefault((event.capture_id, event.episode_id), []).append((cid, event.event_id, tool_name))
        return event

    def finished(self, event: TraceEvent, *, host_call_id: str | None,
                 tool_name: str | None = None) -> TraceEvent:
        if host_call_id:
            event.payload["host_call_id"] = host_call_id
            key = (event.capture_id, event.episode_id, host_call_id)
            parent = self._by_id.pop(key, None)
            self._remove_open(event.capture_id, event.episode_id, host_call_id)
            if parent is not None:
                event.parent_event_id = parent
                event.payload["correlation"] = {"method": "host_call_id", "fidelity": "exact"}
            else:
                event.payload["correlation"] = {"method": "host_call_id", "fidelity": "missing_start"}
            return event

        parent = self._infer_single_open(event.capture_id, event.episode_id, tool_name)
        if parent is None:
            event.payload["correlation"] = {"method": "adapter_local", "fidelity": "ambiguous_or_missing"}
            return event
        cid, event_id = parent
        event.payload["host_call_id"] = cid
        event.parent_event_id = event_id
        event.payload["correlation"] = {"method": "adapter_local", "fidelity": "inferred"}
        self._by_id.pop((event.capture_id, event.episode_id, cid), None)
        return event

    def _infer_single_open(self, capture_id: str, episode_id: str,
                           tool_name: str | None) -> tuple[str, str] | None:
        key = (capture_id, episode_id)
        candidates = [(cid, eid, tool) for cid, eid, tool in self._open.get(key, [])
                      if tool_name is None or tool == tool_name]
        if len(candidates) != 1:
            return None
        cid, event_id, _tool = candidates[0]
        self._remove_open(capture_id, episode_id, cid)
        return cid, event_id

    def _remove_open(self, capture_id: str, episode_id: str, host_call_id: str) -> None:
        key = (capture_id, episode_id)
        self._open[key] = [item for item in self._open.get(key, []) if item[0] != host_call_id]


def host_call_id(payload: dict[str, Any]) -> str | None:
    """Common field names used by host hook payloads for a tool-call id."""
    for key in ("call_id", "tool_call_id", "tool_use_id", "invocation_id", "id"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


__all__ = ["ToolCallCorrelator", "host_call_id"]
