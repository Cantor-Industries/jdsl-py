# Using the jdsl harness & compiler

A hands-on guide to capturing frontier-model behavior and compiling it into a
portable `.jdslpkg` that a smaller frozen model runs. Every command here is
exercised end-to-end; for how the code maps to the design see
[harness.md](./harness.md), and for the full rationale see
[jdsl_behaviour_compiler.md](./jdsl_behaviour_compiler.md).

The loop is always the same four verbs:

```
capture ──▶ inspect ──▶ compile ──▶ run
 (observe)  (lineage)   (.jdslpkg)  (small model)
```

## Install

```bash
uv sync                      # runtime core + harness
uv sync --extra harness      # + the optional MCP control plane (mcp SDK)
```

The `jdsl` runtime core is dependency-light; the compiler and adapters live in the
separate `jdsl_harness` package, and the MCP SDK is only needed for the live
control plane. Nothing below needs a network or an API key — the examples use
frozen fake models.

## Where the store lives

The harness keeps everything (SQLite index, append-only JSONL event spools,
content-addressed blobs) under one directory. Override it per-shell:

```bash
export JDSL_HARNESS_HOME=/path/to/store     # default: ~/.local/share/jdsl-harness
```

Point this at a scratch dir while experimenting so captures stay isolated.

---

## 1. Capture

There are three capture tiers (design §8). They all land in the same canonical
event schema, so `inspect`/`compile` treat them identically — they differ only in
how much they can *see*, which is recorded as a fidelity level (F0–F4).

### Tier A — gateway / jdsl-native (highest fidelity)

A jdsl skill records itself when you attach a `trace_sink`. Every `act`/`react`
leaf emits its tool call with arguments, result, and blackboard state:

```python
from jdsl_harness.store import HarnessStore
from jdsl_harness.capture import CaptureCoordinator

store = HarnessStore("/path/to/store")
coord = CaptureCoordinator(store)
cap = coord.start(host="jdsl", adapter="runtime")

for row in dataset:
    skill.run(trace_sink=store.sink(cap), capture_id=cap, episode_id=row.id, **row.inputs)
    coord.mark_outcome(cap, row.id, reward=row.reward)   # optional supervision
coord.finish(cap)
```

For non-jdsl tools, wrap them with `ToolGateway`, or route MCP tools through
`MCPProxy` — both record the same canonical call events.

### Tier B — host hooks (Claude Code / Gemini CLI / OpenCode)

Start the daemon, then let a host forward its structured hook payloads to it.

```bash
jdsl harness serve                 # loopback ingest on http://127.0.0.1:8848
```

Install the plugin/extension:

```text
plugins/jdsl-claude-plugin/
plugins/jdsl-gemini-extension/
plugins/jdsl-opencode-plugin/
```

The forwarder posts each host's **structured JSON** hook payload — never scraped
terminal text — to the daemon. Route events into a named capture and tune the
hot-path budget with env vars:

| var | default | meaning |
|-----|---------|---------|
| `JDSL_INGEST_URL` | `http://127.0.0.1:8848` | ingest daemon base URL |
| `JDSL_CAPTURE_ID` | `cap_claude` / `cap_gemini` / `cap_opencode` | capture to route into |
| `JDSL_HOOK_TIMEOUT` | `0.5` | max seconds to wait on the hot path |

The forwarder **fails open** (§7.2): if the daemon is down, slow, or the payload
is malformed, the hook still exits 0 with empty output and never blocks or fails a
tool call. Capture is best-effort — observation must never take the agent down.

When the host supplies a stable tool-call id, hook events preserve it as
`host_call_id` and completions are linked to their corresponding
`tool.call.started` event with `parent_event_id`. If a host omits the id, the
adapter marks the correlation as inferred or ambiguous rather than silently
claiming exact fidelity.

> Fidelity note: pure host hooks see tool calls but not the model's private
> reasoning, so a choice like "which order" can look like a constant across
> episodes. `inspect` reports the fidelity the evidence actually supports; a
> gateway/native capture (Tier A) that also records the decision output gives the
> compiler more to work with.

See [docs/opencode.md](./opencode.md) for OpenCode-specific installation and
smoke-test notes.

### Tier C — import foreign logs

Map an existing agent/benchmark log (τ-bench-style JSONL, one episode per line)
into canonical events:

```bash
jdsl capture import runs.jsonl --capture cap_imported
```

Each line is `{"episode_id": "...", "steps": [{tool, args, result, error?}, ...], "outcome": {"reward": 1.0}}`.

### See what you captured

```bash
jdsl capture list
# cap_retail    recording  episodes=2
# cap_imported  recording  episodes=3
```

---

## 2. Inspect — the exact-lineage report (§51)

Before compiling, look at what the traces actually contain. `inspect` prints, per
episode, the exact value flows it found (an output field copied verbatim into a
later argument) and the deterministic candidates it will try to compile:

```bash
jdsl capture inspect cap_retail
```

```json
{
  "episodes": [
    { "episode_id": "ep_a", "tool_calls": 4, "exact_value_flows": 3,
      "flows": [
        { "from": "lookup_out_0.id",        "to": "list_orders.customer_id" },
        { "from": "list_orders_out_1[1].id", "to": "get_order.order_id" },
        { "from": "get_order_out_2.id",      "to": "cancel.order_id" } ] } ],
  "deterministic_candidates": [
    { "type": "DATAFLOW", "claim": { "source": "lookup_out_0.id",
        "target": { "tool": "list_orders", "argument": "customer_id" } },
      "evidence": { "support": 2, "counterexamples": 0 }, "grade": "E1" } ]
}
```

`exact_value_flows` are the id-copies the compiler will replace with references;
`support`/`counterexamples` are counted from the traces, never guessed.

---

## 3. Compile — traces → verified `.jdslpkg`

```bash
jdsl compile cap_retail --name retail --out retail.jdslpkg
```

The pipeline (all deterministic) runs normalize → consolidate → staticize →
verify → package, then prints a report:

```json
{
  "name": "retail",
  "verification": { "status": "passed", "replay_coverage": 1.0,
                    "replay_checks": 6, "replay_passed": 6 },
  "stats": {
    "meaningful_decisions": 4,
    "model_dependent_decisions": 0,
    "residual_decision_burden": 0.0,
    "deterministic_coverage": 1.0,
    "exact_dataflow_refs": 3,
    "inputs": ["email"]
  },
  "required_capabilities": ["cancel", "get_order", "list_orders", "lookup"]
}
```

Reading the metrics (design §33):

| field | meaning |
|-------|---------|
| `residual_decision_burden` | fraction of decisions still left to the model (lower is better) |
| `deterministic_coverage` | fraction the compiler made deterministic |
| `exact_dataflow_refs` | id-copies replaced by references |
| `inputs` | args with no dataflow source that vary across episodes — the package's run inputs |
| `replay_coverage` | fraction of deterministic refs/guards that reproduced the recorded values |

**What the compiler removes.** For the retail cancellation it turns exact id
copying into references and, when a decision output is observed, links an array
index to it (§49):

```
lookup(email = <run input>)               → store customer
list_orders(customer_id = customer.id)    → store orders          # DATAFLOW ref
get_order(order_id = orders[$idx].id)      → store order          # ref + decision link
cancel(order_id = order.id)                                       # DATAFLOW ref
```

The small model no longer decides sequencing, copies ids, or picks tools. Note
`email` here has no dataflow source and differs across episodes, so it compiles to
a **run input** (`{"ref": "email"}`), not a baked-in constant — you supply it at
run time. A value identical across *every* episode stays a constant.

---

## 4. Run — bind host tools and execute

A package ships **no code** — only restricted IR referencing trusted host tools by
logical id. You supply those tools in a small Python file:

```python
# tools.py
def lookup(email):            return db.customer_by_email(email)
def list_orders(customer_id): return db.orders_for(customer_id)
def get_order(order_id):      return db.order(order_id)
def cancel(order_id):         return db.cancel(order_id)

TOOLS = {"lookup": lookup, "list_orders": list_orders,
         "get_order": get_order, "cancel": cancel}
# PREDICATES = {...}   # optional: callables for any guard-call nodes
```

Then inspect, verify, and run:

```bash
jdsl package inspect retail.jdslpkg      # manifest, capabilities, reads/writes, verification
jdsl package verify  retail.jdslpkg      # structural + digest verification (exit non-zero on failure)
jdsl package run     retail.jdslpkg --tools tools.py --input email=carol@example.com
```

```
  get_order(ord_c2)
  → cancel(ord_c2)
  blackboard: {'email': 'carol@example.com', 'lookup_out_0': {...},
               'list_orders_out_1': [...], 'get_order_out_2': {...},
               'cancel_out_3': {'ok': True, 'cancelled': 'ord_c2'}}
```

Add `--model <small-model-id>` to bind a real model to any residual `predict`/
`react` leaves; with none, deterministic packages (RDB 0.0) run without a model at
all. The same package runs unchanged with a *different* small model — portability
is a first-class goal (§34.3).

When a package reaches a residual `predict` leaf, the runtime emits one
`model.requested` event and one `model.responded` event. The request records the
node/signature identity, field names, model id, output schema, and prompt; the
response records raw text where capture policy permits, the parsed semantic value,
elapsed time, and success/failure status:

```json
{
  "kind": "model.responded",
  "payload": {
    "node_id": "resolve_target",
    "signature_id": "resolve_target_order",
    "kind": "predict",
    "model_id": "small-model",
    "output_fields": ["selected_index"],
    "raw_output": "1",
    "parsed_output": 1,
    "elapsed_ms": 18.2,
    "status": "success"
  }
}
```

### Safety of `package run` (§45)

Loading verifies the format, every file digest, and the IR structure **before**
binding any tool. It rejects unknown node types, unbound capabilities, bad
digests, unbounded loops, and unsupported schema versions. Guards are a fixed
operator set over references/paths — never arbitrary code. A missing required
capability fails the bind, never a half-executed run.

---

## Measuring the win (§33/§34)

Final pass rate is necessary but not sufficient. `jdsl_harness.metrics` computes
the burden metrics from a compiled package and summarizes an A/E experiment:

```python
from jdsl_harness.metrics import package_metrics, compare_arms, ArmResult

m = package_metrics(result.package.ir)      # RDB, coverage, tool branching, dataflow rate

compare_arms([
    ArmResult("raw agent",              pass_rate=0.40, active_policy_tokens=120, tool_branching_factor=15, residual_decision_burden=1.00),
    ArmResult("text skill",             pass_rate=0.50, active_policy_tokens=200, tool_branching_factor=15, residual_decision_burden=1.00),
    ArmResult("frontier-compiled jdsl", pass_rate=0.70, active_policy_tokens=12,  tool_branching_factor=0,  residual_decision_burden=0.25),
])   # -> {"success": True, ...}: beats both arms with lower tokens/branching/burden
```

---

## Troubleshooting

| symptom | cause / fix |
|---------|-------------|
| `capture list` empty after a Tier-B run | daemon not running, or `JDSL_CAPTURE_ID` differed — start `jdsl harness serve` and re-drive |
| `replay_coverage < 1.0` | a proposed ref/guard didn't reproduce recorded values; check `verification.problems` in the compile report |
| `KeyError: ref('x') is not on the blackboard` at run time | `x` is a declared input — pass `--input x=...` (see the manifest's `inputs`) |
| `no tool bound for capability 'foo'` | `tools.py` `TOOLS` is missing a required logical id — see `package inspect` → reads |
| MCP control plane errors | install the extra: `uv sync --extra harness` |

## Command reference

| command | purpose |
|---------|---------|
| `jdsl harness serve` | run the loopback ingest daemon (Tier-B data plane) |
| `jdsl capture list` | list captures in the store |
| `jdsl capture import <file> -c <id>` | import foreign JSONL logs (Tier C) |
| `jdsl capture inspect <id>` | exact-lineage report (§51) |
| `jdsl compile <id> -n <name> -o <pkg>` | compile a capture to a verified `.jdslpkg` |
| `jdsl package inspect <pkg>` | manifest, capabilities, verification |
| `jdsl package verify <pkg>` | structural + digest verification |
| `jdsl package run <pkg> -t tools.py [-m model] [-i k=v]` | bind host tools and run |
