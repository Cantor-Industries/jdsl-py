# Branching Triage

This tutorial shows the core jdsl pattern: the model makes one local decision,
then deterministic tree code handles the branches.

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
        predict(
            "message -> category",
            instructions="Return exactly one of: billing, support, other.",
        ),
        sel(
            seq(check("category", "billing"), act(route_to_billing)),
            seq(check("category", "support"), act(route_to_support)),
            act(route_to_human),
        ),
    ))
)
```

Run the fuller example:

```bash
uv run jdsl run examples/pipeline.py -i ticket="my card was charged twice"
```

## Why the Branches Are Deterministic

`predict("message -> category")` writes `category` to the blackboard. The
`selector` then tries children in order:

1. billing branch
2. support branch
3. human fallback

The model does not choose a function to call. It only produces a field, and
`check` consumes that field.

## Multi-Output Classification

The same pattern works when the model writes more than one field:

```python
predict(
    "ticket -> category, urgency",
    instructions="category is one of: bug, billing, question. urgency is one of: low, high.",
)
```

With multiple outputs, jdsl asks for JSON and writes each declared key onto the
blackboard. A later branch can guard on any of those keys.
