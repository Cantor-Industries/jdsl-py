"""Trace sinks (design §35 PR1, §53 principle 2).

A `TraceSink` is where the runtime and adapters send `TraceEvent`s. The default
is `NullTraceSink` — the interpreter behaves exactly as before when nobody is
capturing. Real sinks assign the per-episode `sequence`, seal the hash chain, and
persist or buffer.

The telemetry-plane rule from §7.2 lives here: `emit` must be cheap and must
*fail open* for pure observation. A sink that raises will never abort a run;
`SafeSink` wraps any sink to guarantee that.
"""

from __future__ import annotations

import sys
import threading
from typing import Protocol, runtime_checkable

from jdsl.trace.events import TraceEvent


@runtime_checkable
class TraceSink(Protocol):
    """Where trace events go. `emit` returns the (possibly enriched) event so a
    caller can read back the assigned sequence / hash for parent linkage."""

    def emit(self, event: TraceEvent) -> TraceEvent: ...


class NullTraceSink:
    """Drops everything. The default in `RunContext`; keeps existing behavior
    identical when capture is off."""

    def emit(self, event: TraceEvent) -> TraceEvent:
        return event


class _Chainer:
    """Per-episode sequence counter + hash-chain tail. Shared by the buffered and
    persisted sinks so the chaining rule lives in exactly one place."""

    def __init__(self) -> None:
        self._seq: dict[str, int] = {}
        self._tail: dict[str, str | None] = {}
        self._lock = threading.Lock()

    def stamp(self, event: TraceEvent) -> TraceEvent:
        with self._lock:
            ep = event.episode_id
            seq = self._seq.get(ep, 0)
            event.sequence = seq
            self._seq[ep] = seq + 1
            event.chain(self._tail.get(ep))
            self._tail[ep] = event.event_hash
            return event


class ListTraceSink:
    """Collects events in memory. Ideal for tests and for a single in-process run
    whose events are handed straight to the compiler."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []
        self._chain = _Chainer()

    def emit(self, event: TraceEvent) -> TraceEvent:
        self._chain.stamp(event)
        self.events.append(event)
        return event

    def episode(self, episode_id: str) -> list[TraceEvent]:
        return [e for e in self.events if e.episode_id == episode_id]


class SafeSink:
    """Wrap any sink so `emit` never raises (fail-open observation, §7.2). A
    broken telemetry path must not take the agent down with it."""

    def __init__(self, inner: TraceSink, *, warn: bool = True) -> None:
        self.inner = inner
        self.warn = warn
        self.errors = 0

    def emit(self, event: TraceEvent) -> TraceEvent:
        try:
            return self.inner.emit(event)
        except Exception as err:  # noqa: BLE001 — deliberately swallow to fail open
            self.errors += 1
            if self.warn:
                print(f"[jdsl.trace] sink error (dropped event {event.kind}): {err}", file=sys.stderr)
            return event


class FanoutSink:
    """Emit to several sinks (e.g. an in-memory list plus a JSONL file). The first
    sink assigns sequence/hash; the rest see the already-stamped event."""

    def __init__(self, *sinks: TraceSink) -> None:
        self.sinks = list(sinks)

    def emit(self, event: TraceEvent) -> TraceEvent:
        for i, sink in enumerate(self.sinks):
            if i == 0:
                event = sink.emit(event)
            else:
                sink.emit(event)
        return event


__all__ = ["TraceSink", "NullTraceSink", "ListTraceSink", "SafeSink", "FanoutSink", "_Chainer"]
