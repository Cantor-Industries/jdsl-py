"""Timeline reconstruction from a canonical event stream (design §11.3, §32.2).

The trace layer stores *what happened*. This module rebuilds usable views over an
episode without interpreting it: the ordered timeline, the reconstructed
blackboard state after each write, and the tool-call sequence. The compiler's
verifier (§32.2) replays deterministic behavior against these views; here we only
reconstruct, we never judge.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from jdsl.trace.events import EventKind, TraceEvent


@dataclass
class ToolInvocation:
    """A single tool call reconstructed from started/completed/failed events."""
    logical_id: str | None
    host_name: str | None
    arguments: dict[str, Any]
    result: Any = None
    error: Any = None
    ok: bool = True
    sequence: int = 0

    @property
    def name(self) -> str:
        return self.logical_id or self.host_name or "unknown"


@dataclass
class Episode:
    """One reconstructed episode: its ordered events plus derived views."""
    episode_id: str
    events: list[TraceEvent] = field(default_factory=list)

    def ordered(self) -> list[TraceEvent]:
        return sorted(self.events, key=lambda e: e.sequence)

    def tool_calls(self) -> list[ToolInvocation]:
        """Pair up tool.call.started with the following completed/failed event."""
        calls: list[ToolInvocation] = []
        pending: dict[str | None, ToolInvocation] = {}
        for e in self.ordered():
            if e.kind == EventKind.TOOL_CALL_STARTED:
                tool = e.payload.get("tool", {})
                inv = ToolInvocation(
                    logical_id=tool.get("logical_id"),
                    host_name=tool.get("host_name"),
                    arguments=e.payload.get("arguments", {}) or {},
                    sequence=e.sequence,
                )
                pending[e.event_id] = inv
                calls.append(inv)
            elif e.kind in (EventKind.TOOL_CALL_COMPLETED, EventKind.TOOL_CALL_FAILED):
                inv = pending.get(e.parent_event_id or "")
                if inv is None and calls:
                    inv = calls[-1]  # best-effort pairing when parent linkage is absent
                if inv is not None:
                    if e.kind == EventKind.TOOL_CALL_FAILED:
                        inv.ok = False
                        inv.error = e.payload.get("error")
                    else:
                        inv.result = e.payload.get("result")
        return calls

    def blackboard_states(self) -> list[tuple[int, dict[str, Any]]]:
        """Cumulative blackboard snapshots after each blackboard.write, keyed by
        the event sequence. Reconstructs `state before each decision`."""
        state: dict[str, Any] = {}
        out: list[tuple[int, dict[str, Any]]] = []
        for e in self.ordered():
            if e.kind == EventKind.BLACKBOARD_WRITE:
                state[e.payload["key"]] = e.payload.get("value")
                out.append((e.sequence, dict(state)))
        return out

    def final_blackboard(self) -> dict[str, Any]:
        states = self.blackboard_states()
        return states[-1][1] if states else {}

    def outcome(self) -> dict[str, Any] | None:
        for e in reversed(self.ordered()):
            if e.kind in (EventKind.ENVIRONMENT_REWARD, EventKind.ENVIRONMENT_VERDICT):
                return e.payload
        return None

    def succeeded(self) -> bool | None:
        out = self.outcome()
        if out is None:
            return None
        if "reward" in out:
            return bool(out["reward"])
        if "verdict" in out:
            return str(out["verdict"]).lower() in ("pass", "success", "true", "ok")
        return None


def segment_episodes(events: Iterable[TraceEvent]) -> list[Episode]:
    """Group a flat event stream into episodes (§24 "segment episodes")."""
    order: list[str] = []
    by_id: dict[str, Episode] = {}
    for e in events:
        ep = by_id.get(e.episode_id)
        if ep is None:
            ep = Episode(episode_id=e.episode_id)
            by_id[e.episode_id] = ep
            order.append(e.episode_id)
        ep.events.append(e)
    return [by_id[i] for i in order]


__all__ = ["ToolInvocation", "Episode", "segment_episodes"]
