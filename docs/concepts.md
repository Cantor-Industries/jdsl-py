# Concepts

jdsl combines two ideas:

1. A **behavior tree** gives you deterministic, auditable control flow.
2. A **DSPy-style signature** gives you a typed LLM call at the leaves.

Determinism lives in the tree. The model lives only where you put a `predict`
or `react`.

## The tree

A skill is a tree of nodes. Every node `tick`s to a `Status` — `SUCCESS` or
`FAILURE` — and parents combine those results:

| Node | Rule |
| ---- | ---- |
| `sequence` | Run children left to right; stop at the first `FAILURE` (AND). |
| `selector` | Run children left to right; stop at the first `SUCCESS` (OR). |
| `action` | Call a Python function. "Didn't raise" = `SUCCESS`. |
| `check` | Compare a blackboard value; `SUCCESS` iff it matches. |
| `predict` | Call the model against a signature; `SUCCESS` iff it produced valid output. |
| `react` | Let the model choose among a scoped tool set until it returns a final answer. |
| `root` | The entry point: one child plus name / system prompt / model. |

This is the classic behavior-tree vocabulary from robotics and game AI. It is a
good fit when you want mostly scripted flow with a few model-decided branch
points.

## The blackboard

Nodes don't pass values as function returns; they share a **blackboard** (a dict)
for the duration of one run. It's the behavior-tree analogue of DSPy's field
values.

- Seed it with keyword inputs: `skill.run(message="…")`.
- Capture an action's return value with `store(act(fn), "key")`.
- Read a value into a later action's argument with `ref("key")`.
- `predict("a -> b")` reads input field `a` from the blackboard and writes
  output field `b` back to it.

```python
seq(
    store(act(search, ref("query")), "hits"),   # query in → hits out
    predict("hits -> best"),                     # hits in → best out
    store(act(fetch, ref("best")), "content"),   # best in → content out
)
```

## Signatures

A `predict` leaf is declared by a signature string:

```
"question -> answer"
"titles -> selected_title"
"context, question -> answer, confidence"
```

Left of `->` are input fields read from the blackboard. Right of `->` are output
fields written back to it.

For one output field, jdsl stores the model reply as plain text after stripping
outer whitespace. For multiple output fields, jdsl asks for a JSON object and
parses it leniently from the response. Because the output is structured, a
`selector` can branch on it deterministically with `check`.

That split is the point: behavior-tree determinism for control flow, a signature
for each model leaf.

## `predict` vs `react`

Use `predict` when the model should answer one local question and write fields:

```python
predict("ticket -> category, urgency")
```

Use `react` when the model should choose among tools and chain tool results
inside one leaf:

```python
react("question -> answer", tools=[search, fetch, summarize], max_steps=8)
```

The outer tree stays deterministic either way. `react` only moves the agentic
tool loop into a leaf.

## Why no codegen

The TypeScript ancestor of this project compiled object literals into generated
service modules. jdsl interprets the tree in memory instead. That keeps the
authoring API as plain nested Python calls and lets `act` keep useful type
checking for literal arguments.

The tradeoff: a `ref(...)` argument is only known at run time, so it cannot be
statically checked against the tool signature.

## Execution model

`skill.run(**inputs)`:

1. builds a `RunContext` (blackboard seeded with `inputs`, an empty
   `ContextWindow`, the model + model id),
2. ticks the root, which pushes its `system` text onto the context window and
   descends into its child,
3. each node with a `context=` pushes its own system fragment for the duration
   of its subtree (scoped, then popped),
4. returns the final `RunContext`; read results from `ctx.blackboard`.

The interpreter is synchronous today.

## Failure Model

Every node returns `Status.SUCCESS` or `Status.FAILURE`.

- A Python tool that raises propagates the exception.
- A Python tool that returns `Status.FAILURE` lets parent selectors recover.
- `predict` fails on empty output, unparseable multi-output JSON, or schema
  validation failure in compiled signatures.
- `react` fails if the model gives no final answer or reaches `max_steps`.
- `optional(child)` runs the child but reports success.
- `invert(child)` flips success and failure.
