# Trace and Capture

Tracing connects the runtime to the harness compiler. The runtime can execute
without tracing; adding a trace sink makes it emit canonical events.

Source map:

| Area | Implementation |
| --- | --- |
| event model | [`jdsl/trace/events.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/trace/events.py) |
| sinks | [`jdsl/trace/sink.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/trace/sink.py) |
| JSONL storage | [`jdsl/trace/jsonl.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/trace/jsonl.py) |
| episode replay | [`jdsl/trace/replay.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/trace/replay.py) |
| harness store | [`jdsl_harness/store.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/store.py) |
| ingest server | [`jdsl_harness/server.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/server.py) |

## Event Envelope

Every observation becomes a `TraceEvent`:

```json
{
  "schema_version": "jdsl.trace.v1",
  "event_id": "...",
  "capture_id": "cap_retail",
  "episode_id": "ep_1",
  "sequence": 12,
  "timestamp": "2026-09-01T10:00:00.000Z",
  "source": {"host": "jdsl", "adapter": "runtime", "model": null},
  "actor": "model",
  "kind": "tool.call.started",
  "parent_event_id": null,
  "payload": {
    "tool": {"host_name": "lookup", "logical_id": null},
    "arguments": {"email": "ada@example.com"}
  },
  "prev_event_hash": "sha256:...",
  "event_hash": "sha256:..."
}
```

The payload is deliberately flexible; the envelope is stable.

## Hash Chain

Sinks assign sequence numbers and call `TraceEvent.chain(prev_hash)`. The event
hash covers the event body plus the previous event hash, so the JSONL spool is
tamper-evident in order.

`TraceEvent` itself does not know where it will be stored. Sinks are responsible
for stamping sequence numbers and sealing the chain. This keeps adapters simple:
they construct events, and the store decides the final event order.

`verify_chain` in `jdsl/trace/jsonl.py` can later check that every self-hash and
previous hash still matches.

## Runtime Events

With `trace_sink` set, the interpreter emits:

| Event | Produced by |
| --- | --- |
| `episode.started` / `episode.finished` | `Root.run` |
| `node.enter` / `node.exit` | `Node.tick` |
| `tool.call.started` | `Action` and `React` |
| `tool.call.completed` / `tool.call.failed` | `Action` and `React` |
| `model.requested` / `model.responded` | `Predict` and `React` |
| `blackboard.write` | `Blackboard.set` via `RunContext._install_trace` |
| `toolset.exposed` | `React` and MCP proxy |

Those events are enough for the compiler to recover sequencing, arguments,
results, dataflow, and residual model decisions.

## Store Layout

`HarnessStore` writes:

```text
harness.db
captures/<capture_id>.jsonl
blobs/sha256/<digest>
```

SQLite is an index. The JSONL event stream and blob store are the durable
behavior evidence.

The store deliberately uses boring storage:

- JSONL is append-only evidence
- SQLite is a rebuildable metadata index
- blobs are content-addressed files

That matters for compilation because raw evidence should not be rewritten when
the compiler learns a better interpretation.

## Ingest Server

`IngestServer` exposes loopback HTTP endpoints:

| Endpoint | Input |
| --- | --- |
| `POST /ingest` | canonical `TraceEvent` dict |
| `POST /hook/claude?cap=...` | Claude Code hook payload |
| `POST /hook/gemini?cap=...` | Gemini CLI hook payload |
| `POST /hook/opencode?cap=...` | jdsl OpenCode envelope |
| `GET /captures` | capture list |
| `GET /capture/<id>/summary` | capture summary |

Bad hook payloads return `{ "ok": false }` with HTTP 200. Capture should fail
open so observation does not break the host agent loop.

The server also separates two jobs:

| Plane | Code | Purpose |
| --- | --- | --- |
| data plane | `IngestServer` HTTP endpoints | Fast local event ingestion from hooks/proxies. |
| control plane | `CaptureCoordinator`, CLI, optional MCP server | Start/finish captures, inspect lineage, compile. |

That split is why plugin hooks can be small and failure-tolerant.

## Capture Fidelity

The coordinator infers fidelity from event kinds:

- F0: no useful behavior events
- F1: messages
- F2: tool calls
- F3: state snapshots or deltas
- F4: state plus decision context

This matters because the compiler can only trust what the trace actually saw.
