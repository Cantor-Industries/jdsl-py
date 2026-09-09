"""Append-only JSONL event storage (design §30 "JSONL for append-only event
streams", §11.3 append-only Timeline).

One event per line, deterministic serialization (sorted keys). The Timeline is
immutable: the compiler may reinterpret it but never rewrites it. `JsonlTraceSink`
is a `TraceSink` that stamps the hash chain and appends; `read_events` streams a
file back into `TraceEvent`s.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

from jdsl.trace.events import TraceEvent
from jdsl.trace.sink import _Chainer


class JsonlTraceSink:
    """Append events to a `.jsonl` file, one per line. Opens in append mode so an
    interrupted run keeps whatever it already wrote (append-only, §11.3)."""

    def __init__(self, path: str | Path, *, chain: _Chainer | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._chain = chain or _Chainer()
        self._lock = threading.Lock()

    def emit(self, event: TraceEvent) -> TraceEvent:
        self._chain.stamp(event)
        line = event.to_json()
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return event


def read_events(path: str | Path) -> list[TraceEvent]:
    """Load a JSONL trace file into a list of `TraceEvent`s (order preserved)."""
    return list(iter_events(path))


def iter_events(path: str | Path) -> Iterator[TraceEvent]:
    import json
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield TraceEvent.from_dict(json.loads(line))


def verify_chain(events: list[TraceEvent]) -> list[str]:
    """Verify per-episode hash chains (§10.2). Returns a list of human-readable
    problems; an empty list means every chain is intact."""
    problems: list[str] = []
    tails: dict[str, str | None] = {}
    for e in events:
        if not e.verify_hash():
            problems.append(f"event {e.event_id} ({e.kind}) has a bad self-hash")
        expected_prev = tails.get(e.episode_id)
        if e.prev_event_hash != expected_prev:
            problems.append(
                f"event {e.event_id} in {e.episode_id} breaks the chain: "
                f"prev={e.prev_event_hash} expected={expected_prev}"
            )
        tails[e.episode_id] = e.event_hash
    return problems


__all__ = ["JsonlTraceSink", "read_events", "iter_events", "verify_chain"]
