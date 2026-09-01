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
