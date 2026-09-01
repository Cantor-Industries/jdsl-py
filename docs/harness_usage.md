# Using the Harness and Compiler

The harness flow has four verbs:

```text
capture -> inspect -> compile -> run
```

Use this when you have successful tool-using trajectories and want to turn the
reusable parts into executable jdsl policy.

## Install

```bash
uv sync
uv sync --extra harness
```

The `harness` extra is needed for the live MCP control plane and MCP examples.
The compiler and tests use fake models and can run offline.

## Store Location

The harness stores metadata, event spools, and blobs under one directory:

```bash
export JDSL_HARNESS_HOME=/tmp/jdsl-harness
```

If unset, the default is `~/.local/share/jdsl-harness`.

## 1. Capture

### Tier A: jdsl-Native or Gateway

A jdsl skill can record itself when you attach a trace sink:

```python
from jdsl_harness.capture import CaptureCoordinator
from jdsl_harness.store import HarnessStore

store = HarnessStore("/tmp/jdsl-harness")
coord = CaptureCoordinator(store)
cap = coord.start(host="jdsl", adapter="runtime")

skill.run(
    trace_sink=store.sink(cap),
    capture_id=cap,
    episode_id="ep_0",
    email="ada@example.com",
    request="cancel my order",
)

coord.mark_outcome(cap, "ep_0", reward=1.0)
coord.finish(cap)
```

For non-jdsl callables, wrap tools with `ToolGateway`. For MCP tools, use the
MCP proxy path when you need transparent tool-call recording.

### Tier B: Host Hooks

Start the local ingest daemon:

```bash
uv run jdsl harness serve
```

Then install a host shim:

```text
plugins/jdsl-claude-plugin/
plugins/jdsl-gemini-extension/
plugins/jdsl-opencode-plugin/
```

The shims forward structured hook payloads to the loopback server. They fail
open: if capture is unavailable, host tool execution continues.

Common environment:

| Variable | Default | Meaning |
| --- | --- | --- |
| `JDSL_INGEST_URL` | `http://127.0.0.1:8848` | ingest daemon base URL |
| `JDSL_CAPTURE_ID` | host-specific | capture id to route into |
| `JDSL_HOOK_TIMEOUT` | `0.5` | max seconds to wait in the hook |

See [OpenCode Capture](opencode.md) for OpenCode-specific steps.

### Tier C: Imported Logs

Import generic JSONL logs:

```bash
uv run jdsl capture import runs.jsonl --capture cap_imported
```

Each line is one episode:

```json
{"episode_id": "ep_1", "steps": [{"tool": "lookup", "args": {"email": "a@b.com"}, "result": {"id": "C1"}}], "outcome": {"reward": 1.0}}
```

## 2. Inspect

Inspect the captured lineage before compiling:

```bash
uv run jdsl capture list
uv run jdsl capture inspect cap_imported
```

The report shows exact value flows, deterministic candidates, residual semantic
candidates, retries, and episode success.

## 3. Compile

Compile a capture into a `.jdsl` package:

```bash
uv run jdsl compile cap_imported --name retail --out retail.jdsl
```

The report includes verification status, required capabilities, declared run
inputs, exact dataflow refs, deterministic coverage, and residual decision
burden.

## 4. Run

Inspect and verify the package:

```bash
uv run jdsl package inspect retail.jdsl
uv run jdsl package verify retail.jdsl
```

Create a bindings file:

```python
def lookup(email):
    return {"id": "C1", "email": email}

def list_orders(customer_id):
    return [{"id": "O1", "status": "pending"}]

def get_order(order_id):
    return {"id": order_id, "status": "pending"}

TOOLS = {
    "lookup": lookup,
    "list_orders": list_orders,
    "get_order": get_order,
}
```

Run the package:

```bash
uv run jdsl package run retail.jdsl --tools tools.py \
  --input email=ada@example.com \
  --input request="cancel my order"
```

If the package contains residual model leaves, pass `--model <model-id>` or bind
a model programmatically. Deterministic packages run without a model.

## Metrics

The compiler and package metrics focus on model responsibility:

| Metric | Meaning |
| --- | --- |
| `residual_decision_burden` | fraction of meaningful decisions still delegated to the model |
| `deterministic_coverage` | fraction represented by deterministic nodes |
| `exact_dataflow_refs` | arguments replaced by verified refs |
| `inputs` | run inputs inferred from varying unlinked arguments |
| `replay_coverage` | deterministic refs and guards reproduced against traces |

Static package metrics are structural. Runtime latency and true tokenizer counts
require execution telemetry.
