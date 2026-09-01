# Authoring Surface

This page follows user code into the implementation. Start with a small skill:

```python
from jdsl import act, check, predict, root, sel, seq, store, tool

@tool
def inbound_message() -> str:
    return "I was double charged."

@tool
def route_to_billing() -> None:
    print("billing")

skill = (
    root("Triage", system="Classify inbound messages.")
    .model("deepseek-chat")
    .do(seq(
        store(act(inbound_message), "message"),
        predict("message -> category"),
        sel(
            seq(check("category", "billing"), act(route_to_billing)),
            act(lambda: print("fallback")),
        ),
    ))
)
```

Source map:

| Concept | Implementation |
| --- | --- |
| public exports | [`jdsl/__init__.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/__init__.py) |
| combinators | [`jdsl/dsl.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/dsl.py) |
| node classes | [`jdsl/tree.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/tree.py) |
| blackboard/ref state | [`jdsl/context.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/context.py) |

## `@tool`

`@tool` wraps a callable in a lightweight `Tool` dataclass. The wrapper is still
callable, but it also carries:

- `fn`: the original Python callable
- `name`: explicit name or function name
- `description`: explicit description or docstring

`react` uses that metadata to expose tools to the provider's native tool-calling
API. `act` can call either a `Tool` or an ordinary callable.

## Combinators Build Nodes

The DSL functions are constructors with small conveniences:

| DSL function | Runtime node |
| --- | --- |
| `seq(...)` | `Sequence` |
| `sel(...)` | `Selector` |
| `repeat(...)` | `Repeat` |
| `act(...)` | `Action` |
| `check(...)` | `Check` |
| `guard(...)` | `Guard` |
| `predict(...)` | `Predict` |
| `react(...)` | `React` |

The tree structure is the call structure. There is no code generation step for
authored skills.

## Signatures

`predict("message -> category")` is parsed by `_parse_signature` in `dsl.py`.
The left side becomes input field names and the right side becomes output field
names.

```text
"ticket -> category, urgency"
inputs:  ("ticket",)
outputs: ("category", "urgency")
```

The parser intentionally stays simple. Richer typed signatures exist in compiled
packages, but handwritten skills use the compact string form.

## Refs

`ref("message")` creates a `Ref` object. The value is not read when the tree is
constructed. It is resolved by `Action._resolve` at execution time.

This matters because `store(act(...), "message")` can produce a value earlier in
the same run and a later action can consume it:

```python
seq(
    store(act(search_titles, ref("query")), "titles"),
    predict("titles -> selected_title"),
    store(act(fetch_content, ref("selected_title")), "content"),
)
```

## Stable IDs

Most authors can ignore node ids. The DSL accepts `id=` on combinators so
compiled or traced behavior can name a stable node:

```python
predict("request, orders -> selected_index", id="resolve_target")
```

If a traced run has no author id, `assign_runtime_ids` creates a structural path
id for that run. Package identity should use author/compiler ids because
structural paths can shift if the tree changes.
