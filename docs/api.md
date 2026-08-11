# API reference

Everything is imported from the top-level package:

```python
from jdsl import tool, root, seq, sel, repeat, act, check, predict, react, ref, store
from jdsl import invert, optional, timeout, oneshot, render   # decorators + rendering
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
wrapped object is still directly callable. The name/description and the function's
type hints are what [`react`](#reactsignature--toolsinstructionsmax_stepscontext--react)
exposes to the model for function-calling — so annotate tool params and write a
clear description.

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

Guard leaf: `SUCCESS` iff `blackboard[key]` matches `equals`, else `FAILURE`. Put
one at the head of a `seq` inside a `sel` to branch on a `predict` output.

String matches are **lenient** — case-insensitive, and whitespace / surrounding
punctuation are trimmed — because the value is usually fuzzy model text: `"Yes."`,
`" YES "` and `"yes"` all match `check("ok", "yes")`. Non-string values (ints,
etc.) compare with plain `==`, so `check("n", 2)` does not match `"2"`.

### `predict(signature, *, instructions=None, context=None) -> Predict`

DSPy-style LLM leaf. `signature` is `"in1, in2 -> out1, out2"`. Reads the input
fields from the blackboard and writes the outputs back. A **single** output is
stored as the model's raw reply (no JSON envelope, which otherwise makes the model
reason about the wrapper); **multiple** outputs are requested as one JSON object
and parsed leniently (tolerates surrounding prose). Returns `FAILURE` if nothing
parseable came back. `instructions` prepends task guidance to the prompt. Each
leaf is stateless — state flows through the blackboard, not the message list.

### `react(signature, *, tools, instructions=None, max_steps=6, context=None) -> React`

Agentic LLM leaf. Where `predict` is one shot with no tools, `react` lets the
**model** pick and call the given `@tool`s in a loop — native provider
function-calling (Anthropic `tool_use` / OpenAI `tool_calls`), not text parsing.
Each tool's JSON schema is derived from its signature: `str`/`int`/`float`/`bool`
map to their JSON types, `list[T]`/`tuple`/`set` become an `array` (with an
`items` type from `T`), anything else falls back to `string`; args without a
default are required. The loop: ask the model → run the tools it
calls → feed results back → repeat, until it returns a final answer (written to
the single output field) or `max_steps` is hit (`FAILURE`). `FAILURE` also if the
final answer is empty.

`signature` must have exactly one output — the answer. An unknown tool name is
reported back to the model as an observation rather than raising, so it can
recover.

```python
@tool
def population(city: str) -> int:
    """The population of a city."""
    ...

react("question -> answer", tools=[capital_of, population, multiply], max_steps=6)
```

## Decorators

Single-child wrappers that transform a child's status without adding a new
composite type — "a behaviour wearing a different hat" (the idea is borrowed from
[py_trees](https://py-trees.readthedocs.io/)).

### `invert(child) -> Invert`

Flip the child's status: `SUCCESS` ↔ `FAILURE`. Handy for negative guards:
`invert(check("category", "spam"))`.

### `optional(child) -> Optional`

Fail-soft: run the child but always return `SUCCESS`, so a failing step never
aborts its parent `seq`. This is the clean way to make a sequence step "best
effort" (py_trees calls it `FailureIsSuccess`).

### `timeout(child, *, seconds=30.0) -> Timeout`

Run the child with a wall-clock bound; `FAILURE` if it overruns. The child runs
in a worker thread and is *abandoned* on timeout (Python can't kill it), so use
it for read-only / idempotent work such as an LLM or lookup call.

### `oneshot(child) -> OneShot`

Run the child at most once per run, latching and replaying its status on later
ticks. Only observable inside a `repeat` loop; state is per-run (a fresh
`run(...)` starts over).

## Rendering

### `render(node) -> str`

An ASCII-tree rendering of a skill's structure — no execution, no model. Also
available as `jdsl show <file>` on the CLI.

```
root 'Triage' [deepseek-chat]
└─ seq
   ├─ predict(message -> category)
   └─ sel
      ├─ seq
      │  ├─ check(category == 'billing')
      │  └─ act(route_to_billing)
      └─ optional
         └─ act(escalate)
```

## Runtime objects

### `RunContext`

Returned by `skill.run(...)`. Fields:

- `blackboard: Blackboard` — the shared store; read your results here.
- `window: ContextWindow` — accumulated system fragments.
- `model`, `model_id` — the model backing this run.
- `state: dict` — per-run scratch for stateful nodes (e.g. `oneshot`).

### `Blackboard`

A `dict` with **provenance**. Read with normal dict access; every write is
recorded so you can trace and debug a run:

- `set(key, value, *, writer=…)` — write with attribution (nodes pass their own
  label as `writer`; plain `bb[key] = v` records `writer="?"`).
- `activity: list[Write]` — every write, in order (`key`, `value`, `writer`,
  `previous`, `overwrote`).
- `who_wrote(key) -> str | None` — the last writer of a key.
- `clobbers() -> list[Write]` — writes that overwrote a key a **different** writer
  had set. This catches the silent-clobber bug where two leaves share an output
  name; `jdsl run` prints a `⚠` for each.

### `LanguageModel`

The provider-dispatching backend. `LanguageModel.from_config()` builds one from
stored credentials / `.env`. `generate(*, system, messages, model_id) -> str`.
See [providers.md](providers.md).

### `Status`

`Status.SUCCESS` / `Status.FAILURE`. Truthy for `SUCCESS`, so `if node.tick(ctx):`
reads naturally. A `@tool` may return a `Status` to signal failure to a parent
`selector`.
