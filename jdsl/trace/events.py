"""The canonical, host-neutral trace event model (design §10).

Every observation the harness records — whether it came from the in-process jdsl
runtime, a Claude Code hook, a Gemini CLI hook, an MCP proxy, or an imported log
— is normalized into one `TraceEvent` envelope. Events are append-only and form
a per-episode hash chain (§10.2) so a compiler can trust the provenance of the
evidence it mines.

The design keeps the model deliberately small: a fixed set of `kind` strings
(§10.1) over a free-form `payload`. Adapters emit the subset they can observe;
nothing here assumes a particular host.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "jdsl.trace.v1"


class EventKind:
    """The canonical event kinds (§10.1). A class of string constants rather than
    an enum so importers can carry an unknown host kind through untouched while
    still comparing against the known set."""

    CAPTURE_STARTED = "capture.started"
    CAPTURE_FINISHED = "capture.finished"

    EPISODE_STARTED = "episode.started"
    EPISODE_FINISHED = "episode.finished"

    USER_MESSAGE = "user.message"
    ASSISTANT_MESSAGE = "assistant.message"

    MODEL_REQUESTED = "model.requested"
    MODEL_RESPONDED = "model.responded"

    TOOLSET_EXPOSED = "toolset.exposed"

    TOOL_CALL_PROPOSED = "tool.call.proposed"
    TOOL_CALL_STARTED = "tool.call.started"
    TOOL_CALL_COMPLETED = "tool.call.completed"
    TOOL_CALL_FAILED = "tool.call.failed"

    STATE_SNAPSHOT = "state.snapshot"
    STATE_DELTA = "state.delta"

    ENVIRONMENT_REWARD = "environment.reward"
    ENVIRONMENT_VERDICT = "environment.verdict"

    HOST_COMPACTION = "host.compaction"
    HOST_SUBAGENT_STARTED = "host.subagent.started"
    HOST_SUBAGENT_FINISHED = "host.subagent.finished"

    ANNOTATION = "annotation"

    # In-process runtime kinds (PR1/PR2): the tree-walker's own view of a run.
    # Namespaced under `node.`/`react.` so they never collide with host kinds and
    # a consumer can cleanly separate "how jdsl executed" from "what the agent did".
    NODE_ENTER = "node.enter"
    NODE_EXIT = "node.exit"
    BLACKBOARD_WRITE = "blackboard.write"
    REACT_STARTED = "react.started"
    REACT_FINISHED = "react.finished"


# kinds that legitimately carry no host-observed side effect payload
_CONTROL_KINDS = frozenset({
    EventKind.CAPTURE_STARTED, EventKind.CAPTURE_FINISHED,
    EventKind.EPISODE_STARTED, EventKind.EPISODE_FINISHED,
})


@dataclass
class EventSource:
    """Where an event came from (§10 `source`)."""
    host: str = "jdsl"
    adapter: str = "runtime"
    model: str | None = None


@dataclass
class TraceEvent:
    """One canonical trace event. Construct via `TraceEvent.new(...)` so ids and
    timestamps are filled in; seal the hash chain with `.chain(prev_hash)`."""

    kind: str
    capture_id: str
    episode_id: str
    payload: dict[str, Any] = field(default_factory=dict)

    schema_version: str = SCHEMA_VERSION
    event_id: str = ""
    sequence: int = 0
    timestamp: str = ""
    source: EventSource = field(default_factory=EventSource)
    actor: str = "system"  # model | user | environment | system | tool
    parent_event_id: str | None = None

    state_before_ref: str | None = None
    state_after_ref: str | None = None
    blob_refs: list[str] = field(default_factory=list)

    prev_event_hash: str | None = None
    event_hash: str | None = None

    @classmethod
    def new(cls, kind: str, capture_id: str, episode_id: str, *, sequence: int = 0,
            payload: dict[str, Any] | None = None, actor: str = "system",
            source: EventSource | None = None, parent_event_id: str | None = None,
            state_before_ref: str | None = None, state_after_ref: str | None = None,
            blob_refs: list[str] | None = None) -> TraceEvent:
        return cls(
            kind=kind, capture_id=capture_id, episode_id=episode_id,
            payload=payload or {}, actor=actor, sequence=sequence,
            source=source or EventSource(), parent_event_id=parent_event_id,
            state_before_ref=state_before_ref, state_after_ref=state_after_ref,
            blob_refs=list(blob_refs or []),
            event_id=uuid.uuid4().hex,
            timestamp=_now_iso(),
        )

    def _digest_body(self) -> dict[str, Any]:
        """The fields the hash covers: everything identity-bearing except the
        hash itself. `prev_event_hash` is included so the chain is tamper-evident."""
        body = asdict(self)
        body.pop("event_hash", None)
        return body

    def chain(self, prev_event_hash: str | None) -> TraceEvent:
        """Link this event to its predecessor and seal its own digest (§10.2)."""
        self.prev_event_hash = prev_event_hash
        self.event_hash = self.compute_hash()
        return self

    def compute_hash(self) -> str:
        blob = json.dumps(self._digest_body(), sort_keys=True, separators=(",", ":"), default=str)
        return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def verify_hash(self) -> bool:
        return self.event_hash == self.compute_hash()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        """Deterministic one-line JSON for JSONL storage (sorted keys, no spaces)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceEvent:
        data = dict(data)
        src = data.pop("source", None)
        event = cls(**{k: v for k, v in data.items() if k in _FIELD_NAMES})
        if isinstance(src, dict):
            event.source = EventSource(**{k: src.get(k) for k in ("host", "adapter", "model")})
        elif isinstance(src, EventSource):
            event.source = src
        return event

    def is_control(self) -> bool:
        return self.kind in _CONTROL_KINDS


_FIELD_NAMES = frozenset(TraceEvent.__dataclass_fields__.keys()) - {"source"}


def _now_iso() -> str:
    """UTC ISO-8601 with millisecond precision and a trailing Z (§10 example)."""
    t = time.time()
    ms = int((t - int(t)) * 1000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{ms:03d}Z"


__all__ = ["SCHEMA_VERSION", "EventKind", "EventSource", "TraceEvent"]
