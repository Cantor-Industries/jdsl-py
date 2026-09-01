# jdsl behavior harness & compiler

This document maps the implementation to the design in
[`jdsl_behaviour_compiler.md`](./jdsl_behaviour_compiler.md). The harness captures
frontier-model behavior as canonical traces, mines and verifies reusable
structure, and compiles it into a portable `.jdslpkg` a smaller frozen model runs.

> For a task-oriented walkthrough (install, all three capture tiers, compile,
> verify, run, metrics, troubleshooting) see
> [`harness_usage.md`](./harness_usage.md). This page is the design-to-code map.

> Compile frontier-model behavior into executable policy so weaker frozen models
> have less policy to infer. (§52)

## Layout

```
jdsl/                     dependency-light runtime core
├── trace/                canonical event model, sinks, storage, redaction, replay (§10, §11)
├── ir/                   Behavior IR: schema, safe guard expressions, validation, lowering (§21)
└── package/              manifest, contracts, provenance, .jdslpkg export + loader (§22, §45)

jdsl_harness/             capture + compiler (separate package, optional extras — §36)
├── store.py              SQLite metadata + JSONL spool + blobs (§30)
├── capture.py            capture lifecycle + the §51 lineage report
├── gateway.py            Tier-A tool gateway (§8.1)
├── mcp_proxy.py          transparent MCP proxy recording (§8.1.1)
├── server.py            loopback ingest data plane + optional MCP control plane (§7, §28)
├── state.py              environment adapters (§11.2)
├── metrics.py            §33 metrics + §34 experiment comparison
├── adapters/             claude_code, gemini_cli, generic_mcp, import_jsonl (§8.2, §8.3, §29)
└── compiler/             normalize → lineage → candidates → consolidate → model
                          → staticize → residualize → verify → package (§13–§24)

plugins/                  thin host shims (§29): Claude Code plugin, Gemini CLI extension
```

## The pipeline (§24)

```
canonical traces
  → normalize        symbolic steps + exact dataflow lineage (§13, §16.1)
  → consolidate      support / counterexamples / evidence grades E0–E5 (§14.2, §15)
  → staticize        modal skeleton → refs, guards, recovery, residual leaves (§17, §25)
  → verify           structural + trace-replay; promote replay-verified to E4 (§32)
  → package          verified BehaviorPackage → .jdslpkg (§22)
```

One call runs the whole thing:

```python
from jdsl.trace import segment_episodes
from jdsl_harness.compiler import compile_behavior

result = compile_behavior(episodes, name="retail-cancellation", task_family="retail-support")
print(result.report())          # verification status, RDB, capabilities
```

The compiler is **deterministic**: exact dataflow, guard truth, support counts,
and replay are computed, never asked of a model. The compiler model (`model.py`)
only proposes hypotheses — signatures and wording — that recorded evidence must
confirm (§24.1). It ships with an offline `HeuristicCompilerModel` so the whole
pipeline runs in CI without a network (§46).

### What compilation removes

For the retail-cancellation example the compiler turns exact id copying into refs
and links the array index to the model's own decision (§49):

```
lookup(email=…)                      → store customer
list_orders(customer_id=customer.id) → store orders          # DATAFLOW ref
predict(request, orders -> selected_index)                   # the one residual leaf
get_order(order_id=orders[$selected_index].id) → store order # DATAFLOW + decision link
```

The small model no longer decides sequencing, copies ids, or picks tools — only
the single semantic choice remains (`residual_decision_burden = 0.25`).

## Capture

Three tiers (§8):

- **Tier A — gateway** (preferred): wrap task tools with `ToolGateway` or route MCP
  tools through `MCPProxy`; every call is recorded with arguments, result, and
  state. jdsl-native `Action`/`React` nodes self-record when a `trace_sink` is set.
  The live MCP proxy currently supports one stdio upstream and preserves upstream
  tool schemas while namespacing forwarded tools.
- **Tier B — host hooks**: install the Claude Code plugin or Gemini extension; the
  forwarder posts structured hook payloads to the local ingest daemon.
- **Tier C — import**: `adapters/import_jsonl` maps foreign logs into canonical events.

Start the daemon, then capture:

```bash
jdsl harness serve                        # loopback ingest + store
jdsl capture list
jdsl capture import runs.jsonl -c cap_x   # Tier C: import foreign logs
jdsl capture inspect <capture-id>         # the §51 exact-lineage report
jdsl compile <capture-id> --name retail --out retail.jdslpkg
```

## Running a package

```bash
jdsl package inspect retail.jdslpkg   # manifest, reads/writes, verification
jdsl package verify  retail.jdslpkg   # structural + digest verification
jdsl package run     retail.jdslpkg --tools tools.py --model <small-model>
```

`tools.py` exposes `TOOLS = {logical_id: callable}` (and optional `PREDICATES`).
Loading verifies the package format, file digests, and IR structure before binding
any tool (§45); a missing required capability fails the bind, never a run.

## Safety (§45)

A `.jdslpkg` is executable policy, so it ships **no arbitrary code**: restricted
IR, typed signatures, safe guard expressions, and references to trusted host
tools. Guards are a fixed operator set over refs/paths (`ir/expr.py`); the loader
rejects unknown node types, unbound capabilities, bad digests, unbounded loops,
and unsupported schema versions.

## Status vs. the design

Implemented: PR1–PR13 (trace core, react instrumentation, node ids, canonical
trace package, gateway/proxy, harness daemon, host adapters, deterministic
normalizer, candidate store, compiler-model pass, IR + loader, verifier, package
export) plus the §33 metrics. The live MCP transport (`serve_proxy`) supports a
stdio upstream and the MCP control plane is import-guarded behind the optional
`harness` extra. Additional MCP transports, package signing (§22.4), and
iterative residual decomposition (§26) are left as documented extension points.
