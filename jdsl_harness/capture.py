"""Capture coordination and the lineage report (design §28.1 control ops, §51).

This is the control-plane logic behind both the CLI and the MCP server: start /
finish a capture, mark an episode outcome, summarize, and produce the deterministic
exact-lineage report that §51 names as the first concrete milestone::

    frontier host -> jdsl capture -> canonical trace -> exact lineage report

The coordinator never depends on MCP; the MCP server is a thin shell over it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from jdsl.trace.events import EventKind, TraceEvent
from jdsl_harness.compiler.consolidate import consolidate
from jdsl_harness.compiler.normalize import NormEpisode, normalize_all
from jdsl_harness.store import HarnessStore


@dataclass
class CaptureCoordinator:
    """Owns capture lifecycle and analysis over a `HarnessStore`."""
    store: HarnessStore

    # -- lifecycle (§28.1) ----------------------------------------------------

    def start(self, *, host: str = "jdsl", adapter: str = "runtime", note: str = "") -> str:
        capture_id = "cap_" + uuid.uuid4().hex[:12]
        self.store.start_capture(capture_id, host=host, adapter=adapter, note=note)
        self.store.sink(capture_id).emit(TraceEvent.new(
            EventKind.CAPTURE_STARTED, capture_id, "_capture", payload={"host": host, "adapter": adapter}))
        return capture_id

    def finish(self, capture_id: str) -> None:
        self.store.sink(capture_id).emit(TraceEvent.new(
            EventKind.CAPTURE_FINISHED, capture_id, "_capture", payload={}))
        self.store.finish_capture(capture_id)

    def mark_outcome(self, capture_id: str, episode_id: str, *, reward: float | None = None,
                     verdict: str | None = None) -> None:
        payload: dict[str, Any] = {}
        if reward is not None: payload["reward"] = reward
        if verdict is not None: payload["verdict"] = verdict
        kind = EventKind.ENVIRONMENT_REWARD if reward is not None else EventKind.ENVIRONMENT_VERDICT
        self.store.sink(capture_id).emit(TraceEvent.new(kind, capture_id, episode_id,
                                                        payload=payload, actor="environment"))

    # -- analysis -------------------------------------------------------------

    def summary(self, capture_id: str) -> dict[str, Any]:
        events = self.store.capture_events(capture_id)
        episodes = self.store.capture_episodes(capture_id)
        real = [e for e in episodes if not e.episode_id.startswith("_")]
        return {
            "capture_id": capture_id,
            "events": len(events),
            "episodes": len(real),
            "fidelity": _fidelity(events),
            "outcomes": {e.episode_id: e.succeeded() for e in real},
        }

    def lineage_report(self, capture_id: str) -> dict[str, Any]:
        """The §51 exact-lineage report over a capture's episodes."""
        episodes = [e for e in self.store.capture_episodes(capture_id)
                    if not e.episode_id.startswith("_")]
        norm = normalize_all(episodes)
        per_episode = [_episode_lineage(n) for n in norm]
        candidates = consolidate(norm)
        deterministic = [c.to_dict() for c in candidates
                         if c.type in ("DATAFLOW", "CONTROL") and c.status != "contested"]
        residual = [c.to_dict() for c in candidates if c.type == "SEMANTIC"]
        return {
            "capture_id": capture_id,
            "episodes": per_episode,
            "deterministic_candidates": deterministic,
            "residual_candidates": residual,
        }


def _episode_lineage(n: NormEpisode) -> dict[str, Any]:
    flows = [{"from": s.arg_lineage[a], "to": f"{s.logical_tool}.{a}"}
             for s in n.steps for a in s.arguments if s.arg_lineage.get(a)]
    retries = sum(1 for s in n.steps if not s.ok)
    return {
        "episode_id": n.episode_id,
        "tool_calls": len(n.steps),
        "exact_value_flows": len(flows),
        "flows": flows,
        "retries": retries,
        "semantic_decisions": len(n.decisions),
        "success": n.success,
    }


def _fidelity(events: list[TraceEvent]) -> str:
    """Best fidelity level the evidence supports (§9)."""
    kinds = {e.kind for e in events}
    has_tools = bool(kinds & {EventKind.TOOL_CALL_STARTED})
    has_state = bool(kinds & {EventKind.STATE_SNAPSHOT, EventKind.STATE_DELTA}) or \
        any(e.state_before_ref or e.state_after_ref for e in events)
    has_decision_ctx = bool(kinds & {EventKind.TOOLSET_EXPOSED, EventKind.MODEL_REQUESTED})
    if has_decision_ctx and has_state:
        return "F4"
    if has_state:
        return "F3"
    if has_tools:
        return "F2"
    if kinds & {EventKind.USER_MESSAGE, EventKind.ASSISTANT_MESSAGE}:
        return "F1"
    return "F0"


__all__ = ["CaptureCoordinator"]
