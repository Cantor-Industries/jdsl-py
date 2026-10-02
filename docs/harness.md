# Harness and Compiler

The harness captures observable agent behavior, stores it as canonical traces,
and compiles reusable structure into a portable `.jdsl` package.

The important distinction is procedure versus judgment:

- procedure becomes deterministic tree structure, refs, guards, and fixed
  actions
- remaining judgment becomes a typed residual `predict` or `react` signature

## Current State

The harness is an implemented local capture and compilation pipeline. The
supported path is:

```text
trace or import events
  -> local store
  -> lineage inspection
  -> heuristic compiler
  -> validated .jdsl package
  -> host-bound package runtime
```

Currently implemented:

- Tier A native capture through `TraceSink`, `CaptureCoordinator`,
  `ToolGateway`, and the MCP proxy.
- Tier B loopback HTTP ingestion for Claude Code, Gemini CLI, and OpenCode hook
  payloads. The host adapters normalize payloads into canonical trace events.
- Tier C generic JSONL import for foreign execution logs.
- SQLite metadata, append-only JSONL event spools, and filesystem blobs under
  `JDSL_HARNESS_HOME` or `~/.local/share/jdsl-harness`.
- Capture lifecycle, episode outcomes, summaries, and exact value-lineage
  reports through the coordinator, HTTP endpoints, and optional MCP control
  plane.
- Offline heuristic compilation into restricted Behavior IR, typed residual
  signatures, capability contracts, provenance, replay tests, and deterministic
  `.jdsl` archives.
- Package digest verification, structural IR validation, host capability
  binding, and execution through `jdsl package run`.

The TUI is intentionally **not** a harness console at this stage. `jdsl tui`
is currently the skill-authoring workbench; use the CLI or Python APIs for
capture, inspection, compilation, and package execution.

The harness does not yet provide universal correctness proof. Replay verification
shows fidelity to captured evidence, while held-out task evaluation is still
required. Host hook fidelity also depends on the payload each host exposes, and
the heuristic compiler chooses a representative successful trajectory rather
than solving arbitrary workflows.

## Capability Status

| Area | Status | Current boundary |
| --- | --- | --- |
| Native trace capture and lifecycle | Implemented | `TraceSink`, `CaptureCoordinator`, and `HarnessStore` support local captures and episode outcomes. |
| Host hook ingestion | Implemented | Claude Code, Gemini CLI, and OpenCode adapters accept their current hook envelopes through the loopback daemon. |
| Generic log import | Implemented | JSONL records can be imported and compiled; source fidelity depends on the fields present. |
| Redaction | Experimental | `Redactor` supports patterns, secret-like key names, and configured paths, but is not automatically applied to every durable write. |
| Lineage and candidate extraction | Implemented | Exact flows, controls, semantic decisions, retries, and support/counterexample evidence are reported. |
| Heuristic compilation | Implemented | The modal successful trajectory becomes restricted Behavior IR; unexplained choices remain residual signatures. |
| Multi-trajectory branching | Planned | The current staticizer does not merge arbitrary divergent trajectories into a learned branch tree. |
| Package validation and binding | Implemented | Digests, format, IR structure, signatures, capabilities, and safe guard expressions are checked before binding. |
| Package hardening and signing | Planned | Archive resource limits, signatures, trusted keys, and policy enforcement are not yet shipped. |
| Runtime budgets and dry run | Planned | Tool/model/effect budgets and non-executing policy inspection are not yet enforced. |
| Evaluation runner | Planned | Replay evidence exists; paired held-out evaluation against baselines is not yet a supported workflow. |
| TUI | Implemented, scoped | `jdsl tui` is currently the skill-authoring workbench; harness capture remains in the CLI/API. |

Security details and explicit non-goals are tracked in
[Harness Security Model](security.md).

Source map:

| Layer | Code |
| --- | --- |
| capture lifecycle | [`jdsl_harness/capture.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/capture.py) |
| event store | [`jdsl_harness/store.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/store.py) |
| local ingest | [`jdsl_harness/server.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/server.py) |
| tool gateway | [`jdsl_harness/gateway.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/gateway.py) |
| MCP proxy | [`jdsl_harness/mcp_proxy.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/mcp_proxy.py) |
| compiler | [`jdsl_harness/compiler/`](https://github.com/Cantor-Industries/jdsl-py/tree/harness/jdsl_harness/compiler) |

## Pipeline

```text
canonical traces
  -> normalize
  -> consolidate
  -> staticize
  -> verify
  -> package
```

`normalize` turns raw events into ordered tool steps, observed model decisions,
and exact argument lineage. `consolidate` counts support and counterexamples.
`staticize` builds Behavior IR from the modal successful trajectory. `verify`
checks structure and replay. `package` exports a deterministic archive.

The default compiler model is `HeuristicCompilerModel`, so the current pipeline
can run offline in tests. The design allows richer compiler-model proposal roles,
but the public docs should treat the implemented heuristic path as the baseline.

The full implementation walkthrough is in
[Compiler Internals](code/compiler.md). That page follows the pipeline through
`normalize.py`, `lineage.py`, `candidates.py`, `consolidate.py`,
`staticize.py`, `residualize.py`, `verify.py`, and package assembly.

## What Compilation Removes

For a retail cancellation flow, traces might show:

```text
lookup(email) -> customer
list_orders(customer_id=customer.id) -> orders
predict(request, orders -> selected_index)
get_order(order_id=orders[$selected_index].id) -> order
```

The compiled package does not ask the smaller model to copy ids, pick tools, or
remember sequencing. It asks only for `selected_index`. The runtime then resolves
the exact order id through `orders[$selected_index].id`.

## Capture Tiers

| Tier | Source | Typical fidelity |
| --- | --- | --- |
| A | jdsl-native tracing, `ToolGateway`, or MCP proxy | strongest tool and state visibility |
| B | Claude Code, Gemini CLI, or OpenCode hooks | host tool events, depending on hook payload |
| C | Imported JSONL logs | whatever the source log contains |

All tiers map into the same canonical event schema. The compiler should never
claim more than the recorded events prove.

Tier A has the strongest evidence because jdsl sees structured tool calls and
state directly. Tier B depends on host hook fidelity. Tier C is useful for
benchmarks and migrations, but the compiler can only mine fields that exist in
the imported records.

## Implemented Components

```text
jdsl/trace/       events, JSONL sinks, blobs, redaction, replay
jdsl/ir/          Behavior IR, guard expressions, validation, lowering
jdsl/package/     manifest, contracts, export, load, bind
jdsl_harness/     store, capture coordinator, gateway, server, adapters
compiler/         normalize, candidates, consolidate, staticize, verify, package
plugins/          Claude Code, Gemini CLI, OpenCode shims
```

See [Using the Harness and Compiler](harness_usage.md) for commands and
[Behavior Packages](packages.md) for the archive format.
