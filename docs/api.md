# API reference

Everything is imported from the top-level package:

```python
from jdsl import tool, root, seq, sel, act, check, predict, ref, store
```

## Building blocks

### `@tool`

Register a Python callable as a tool.

```python
@tool
def greet(name: str) -> None: ...

@tool(description="Search Wikipedia and return titles.")
def search(query: str) -> list[str]: ...
```

Usable bare (`@tool`) or with metadata (`@tool(name=…, description=…)`). The
wrapped object is still directly callable. Metadata is carried for a future
LLM-tool-use node; today it's documentation.

### `root(name, *, system=None) -> Root`

The entry point of a skill. Returns a `Root` that is also a small builder:

```python
skill = root("Triage", system="You classify messages.").model("deepseek-chat").do(child)
```

- `.model(model_id)` — sets the model; the **provider is inferred from the id**
  (see [providers.md](providers.md)).
- `.do(child)` — sets the single child node.
- `.run(*, model=None, **inputs) -> RunContext` — execute. `model` may be a
  `LanguageModel`; if omitted and the skill needs one, it's built from stored
  credentials. `inputs` seed the blackboard.

### `seq(*children, context=None) -> Sequence`

Run children in order; return `FAILURE` at the first child that fails, else
`SUCCESS`. Optional `context=` pushes a system fragment for this subtree.

### `sel(*children, context=None) -> Selector`

Run children in order; return `SUCCESS` at the first child that succeeds, else
`FAILURE`.

### `repeat(child, *, until=None, max=3, context=None) -> Repeat`

Run `child` up to `max` times, checking `until` (a node, usually a `check`) after
each pass and stopping early when it succeeds. `SUCCESS` when `until` is satisfied
— or when there's no `until` (a fixed `max`-times loop). `FAILURE` if `max` is
reached unsatisfied, or if `child` fails (which aborts immediately). Do-while, not
while: the body runs before the first `until` check.

```python
repeat(
    seq(predict("draft -> critique, ok"), sel(check("ok", "yes"), predict("draft, critique -> draft"))),
    until=check("ok", "yes"), max=3,
)
```

### `act(fn, *args, **kwargs) -> Action`

A leaf that calls `fn(*args, **kwargs)`.

- Literal args are **type-checked** against `fn`'s signature (`ParamSpec`).
- A `ref("key")` arg is resolved from the blackboard at run time.
- Return value handling: a returned `Status` is honored (so a tool can report
  `FAILURE` to a parent selector); otherwise the node succeeds, and — if wrapped
  in `store` — the return value is written to the blackboard.

### `ref(name) -> Ref`

A placeholder for `blackboard[name]`, resolved when the action runs. Raises
`KeyError` (with guidance) if the key isn't present yet.

```python
act(fetch, ref("selected_title"))
```

### `store(action, key) -> Action`

Capture an action's return value onto the blackboard under `key`. Returns the
same action for inline use:

```python
store(act(search, ref("query")), "titles")
```

### `check(key, equals) -> Check`

Guard leaf: `SUCCESS` iff `blackboard[key] == equals`, else `FAILURE`. Put one
at the head of a `seq` inside a `sel` to branch on a `predict` output.

### `predict(signature, *, instructions=None, context=None) -> Predict`

DSPy-style LLM leaf. `signature` is `"in1, in2 -> out1, out2"`. Reads the input
fields from the blackboard, asks the model for the output fields as JSON, parses
them (lenient — tolerates surrounding prose), writes them back, and appends the
raw reply to the context window. Returns `FAILURE` if nothing parseable came
back. `instructions` prepends task guidance to the prompt.

## Runtime objects

### `RunContext`

Returned by `skill.run(...)`. Fields:

- `blackboard: Blackboard` — the shared dict; read your results here.
- `window: ContextWindow` — accumulated system fragments + messages.
- `model`, `model_id` — the model backing this run.

### `LanguageModel`

The provider-dispatching backend. `LanguageModel.from_config()` builds one from
stored credentials / `.env`. `generate(*, system, messages, model_id) -> str`.
See [providers.md](providers.md).

### `Status`

`Status.SUCCESS` / `Status.FAILURE`. Truthy for `SUCCESS`, so `if node.tick(ctx):`
reads naturally. A `@tool` may return a `Status` to signal failure to a parent
`selector`.
