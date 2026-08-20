"""Trace import adapters (design §8.3).

Benchmarks and existing agent frameworks already emit logs. Every importer maps
into the same canonical jdsl event schema (§8.3). Two importers are provided:

- `import_canonical`: read a jdsl `.jsonl` trace back (round-trip).
- `import_records`: map a generic list of `{tool, arguments, result, ...}` step
  records (τ-style / custom JSONL) into canonical events.

Both record capture fidelity implicitly via the event kinds they emit — an
importer never claims more than its source provides (§8.2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jdsl.trace.events import EventKind, EventSource, TraceEvent
from jdsl.trace.jsonl import read_events


def import_canonical(path: str | Path) -> list[TraceEvent]:
    """Load a canonical jdsl trace file (already in the v1 schema)."""
    return read_events(path)


def import_records(records: list[dict[str, Any]], *, capture_id: str, episode_id: str,
                   host: str = "import", adapter: str = "records",
                   outcome: dict[str, Any] | None = None) -> list[TraceEvent]:
    """Map generic step records into canonical events. Each record may have:
    `tool`/`name`, `arguments`/`args`, `result`/`output`, `error`, `role`+`content`
    (a message), or `type` == 'assistant'/'user'."""
    src = EventSource(host=host, adapter=adapter)
    events: list[TraceEvent] = []

    def add(kind: str, payload: dict[str, Any], actor: str = "system",
            parent: str | None = None) -> TraceEvent:
        e = TraceEvent.new(kind, capture_id, episode_id, payload=payload, actor=actor,
                           source=src, parent_event_id=parent)
        events.append(e)
        return e

    add(EventKind.EPISODE_STARTED, {"host": host})
    for rec in records:
        role = rec.get("role") or rec.get("type")
        tool = rec.get("tool") or rec.get("name")
        if tool:
            started = add(EventKind.TOOL_CALL_STARTED, {
                "tool": {"host_name": tool, "logical_id": rec.get("logical_id")},
                "arguments": rec.get("arguments") or rec.get("args") or {}}, actor="model")
            if rec.get("error"):
                add(EventKind.TOOL_CALL_FAILED, {"tool": {"host_name": tool}, "error": rec["error"]},
                    actor="tool", parent=started.event_id)
            else:
                add(EventKind.TOOL_CALL_COMPLETED, {
                    "tool": {"host_name": tool}, "result": rec.get("result", rec.get("output"))},
                    actor="tool", parent=started.event_id)
        elif role in ("user", "assistant"):
            kind = EventKind.USER_MESSAGE if role == "user" else EventKind.ASSISTANT_MESSAGE
            add(kind, {"text": rec.get("content", "")}, actor=role)
    if outcome:
        kind = EventKind.ENVIRONMENT_REWARD if "reward" in outcome else EventKind.ENVIRONMENT_VERDICT
        add(kind, outcome, actor="environment")
    add(EventKind.EPISODE_FINISHED, {"host": host})
    return events


def import_records_file(path: str | Path, *, capture_id: str, episode_field: str = "episode_id",
                        steps_field: str = "steps") -> list[TraceEvent]:
    """Import a JSONL file where each line is one episode `{episode_id, steps:[...],
    outcome:{...}}`."""
    events: list[TraceEvent] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        events += import_records(obj.get(steps_field, []), capture_id=capture_id,
                                 episode_id=str(obj.get(episode_field, "ep")),
                                 outcome=obj.get("outcome"))
    return events


__all__ = ["import_canonical", "import_records", "import_records_file"]
