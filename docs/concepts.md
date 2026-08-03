# Concepts

jdsl is two ideas glued together:

1. A **behavior tree** gives you deterministic, auditable control flow.
2. A **DSPy-style signature** gives you a typed LLM call at the leaves.

Determinism lives in the tree; the model lives only where you put a `predict`.

## The tree

A skill is a tree of nodes. Every node `tick`s to a `Status` — `SUCCESS` or
`FAILURE` — and parents combine those results:

| Node | Rule |
| ---- | ---- |
| `sequence` | Run children left to right; stop at the first `FAILURE` (AND). |
| `selector` | Run children left to right; stop at the first `SUCCESS` (OR). |
| `action` | Call a Python function. "Didn't raise" = `SUCCESS`. |
| `check` | Compare a blackboard value; `SUCCESS` iff it matches. |
| `predict` | Call the model against a signature; `SUCCESS` iff it answered. |
| `root` | The entry point: one child plus name / system prompt / model. |

This is the classic behavior-tree vocabulary from robotics and game AI. It is a
good fit when you want *mostly scripted* flow with a few model-decided branch
points — not a free-roaming ReAct agent.

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

## Signatures (the DSPy part)

A `predict` leaf is declared by a signature string:

```
"question -> answer"
"titles -> selected_title"
"context, question -> answer, confidence"
```

Left of `->` are input fields (read from the blackboard); right are output
fields (written back). At run time the leaf renders the inputs into a prompt,
asks the model to return exactly those output keys as JSON, parses them, and
writes them onto the blackboard. Because the output is structured, a `selector`
can branch on it deterministically with `check`.

That split — **behavior-tree determinism for control flow, a signature for the
LLM leaf** — is the whole point.

## Why no codegen

The TypeScript ancestor of this project *compiled* behavior-tree object literals
into Effect service modules on disk (via an in-memory TypeScript language
service and an AST factory). jdsl interprets the tree in memory instead. That
deletes a large amount of machinery and is what lets the authoring API be plain
nested function calls with real argument type-checking (`act` is typed with
`ParamSpec`). The one thing you give up: a `ref` argument can't be statically
checked against the tool signature, because its value is only known at run time
— the same tradeoff DSPy makes with field values.

## Execution model

`skill.run(**inputs)`:

1. builds a `RunContext` (blackboard seeded with `inputs`, an empty
   `ContextWindow`, the model + model id),
2. ticks the root, which pushes its `system` text onto the context window and
   descends into its child,
3. each node with a `context=` pushes its own system fragment for the duration
   of its subtree (scoped, then popped),
4. returns the final `RunContext` — read results off `ctx.blackboard`.

The interpreter is synchronous today.
