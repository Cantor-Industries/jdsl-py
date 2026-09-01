# Harness and Compiler

The harness captures observable agent behavior, stores it as canonical traces,
and compiles reusable structure into a portable `.jdsl` package.

The important distinction is procedure versus judgment:

- procedure becomes deterministic tree structure, refs, guards, and fixed
  actions
- remaining judgment becomes a typed residual `predict` or `react` signature

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
