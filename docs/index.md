# jdsl

jdsl is a small Python runtime for behavior-tree agents. You author control flow
with normal function calls (`seq`, `sel`, `repeat`, `act`) and put the model only
where the task needs judgment (`predict` or `react`).

The core rule is simple: deterministic procedure belongs in the tree, values
flow through the blackboard, and model calls have explicit signatures.

```python
from jdsl import act, check, predict, root, sel, seq, tool

@tool
def route_to_billing():
    print("billing")

@tool
def route_to_support():
    print("support")

@tool
def route_to_human():
    print("human")

skill = (
    root("Triage", system="Classify inbound messages: billing, support, other.")
    .model("deepseek-chat")
    .do(seq(
        predict("message -> category"),
        sel(
            seq(check("category", "billing"), act(route_to_billing)),
            seq(check("category", "support"), act(route_to_support)),
            act(route_to_human),
        ),
    ))
)

ctx = skill.run(message="I was double charged.")
print(ctx.blackboard["category"])
```

## Start Here

- [Quickstart](quickstart.md): install, run a deterministic skill, then run an
  LLM-backed branch.
- [Concepts](concepts.md): behavior trees, the blackboard, signatures, and
  scoped context.
- [API Reference](api.md): every public combinator and runtime object.
- [Code Walkthrough](code/authoring.md): how the user-facing API maps to
  `jdsl/dsl.py`, `jdsl/tree.py`, traces, IR, and package binding.
- [Examples](examples.md): which runnable script to start from.
- [Harness Usage](harness_usage.md): capture, inspect, compile, and run portable
  `.jdsl` packages.

## What jdsl Is Optimizing For

jdsl is built around one practical claim: most useful agent behavior is not
improved by asking a model to rediscover procedure on every run. The procedure
should be explicit, testable, and replayable. The model should be called only for
the parts that are actually judgment.

That split shows up everywhere in the code:

| Problem | jdsl answer | Source |
| --- | --- | --- |
| Branching and sequencing | Behavior-tree nodes return `SUCCESS` or `FAILURE`. | [`jdsl/tree.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/tree.py) |
| Values between steps | A per-run blackboard records values and write provenance. | [`jdsl/context.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/context.py) |
| Simple model decisions | `predict` reads named inputs and writes named outputs. | [`jdsl/tree.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/tree.py) |
| Tool-using model loops | `react` exposes scoped tools through native function calling. | [`jdsl/tree.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/tree.py) |
| Capturing behavior | Runtime/hooks/proxies emit canonical `TraceEvent`s. | [`jdsl/trace/events.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/trace/events.py) |
| Compiling behavior | Exact refs and fixed actions are recovered before residual model leaves. | [`jdsl_harness/compiler/`](https://github.com/Cantor-Industries/jdsl-py/tree/harness/jdsl_harness/compiler) |
| Shipping behavior | `.jdsl` packages carry restricted IR, contracts, signatures, and provenance. | [`jdsl/package/`](https://github.com/Cantor-Industries/jdsl-py/tree/harness/jdsl/package) |

The docs under [Code Walkthrough](code/authoring.md) follow those source files
directly.

## Install

```bash
uv sync
uv run jdsl run examples/greeter.py
uv run pytest
```

LLM-backed examples read provider keys from `.env` or stored config. See
[Providers](providers.md).

## Harness and Compiler

jdsl can also compile observed behavior into portable policy. The harness
captures canonical traces, mines and verifies reusable structure, and leaves
semantic residue as typed signatures. The output is a deterministic `.jdsl`
package.

```text
capture -> normalize -> consolidate -> staticize -> verify -> package
```

See [Harness Usage](harness_usage.md) for the hands-on flow and
[Behavior Packages](packages.md) for package structure and binding.

## Current Boundary

The runtime, tracing, offline compiler, package export/load, and host capture
adapters are implemented. Some design notes are intentionally kept in
`docs/drafts/` and are ignored by Git because they describe roadmap work or
experiments, not the public shipped surface.
