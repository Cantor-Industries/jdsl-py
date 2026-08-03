# jdsl

> Declarative **behavior-tree agents** as clean Python combinators, run by a
> **tree-walking interpreter** over Claude / DeepSeek / OpenAI — with
> **DSPy-style signatures** on the LLM leaves.

Determinism lives in the tree (`seq` / `sel` / `act`); the model enters only at
`predict` leaves, typed by a signature like `"message -> category"`. No codegen,
no object-literal DSL — the tree structure *is* the call structure.

```python
from jdsl import tool, root, seq, sel, act, check, predict, ref, store

@tool
def route_to_billing(): print("→ billing")
@tool
def route_to_support(): print("→ support")
@tool
def route_to_human():   print("→ human")

skill = (
    root("Triage", system="Classify inbound messages: billing, support, other.")
    .model("deepseek-chat")                       # provider inferred from the id
    .do(seq(
        predict("message -> category"),           # the model classifies…
        sel(                                      # …and the tree branches on it
            seq(check("category", "billing"), act(route_to_billing)),
            seq(check("category", "support"), act(route_to_support)),
            act(route_to_human),                  # fallback
        ),
    ))
)

ctx = skill.run(message="I was double charged.")
print(ctx.blackboard["category"])                 # -> "billing"
```

## Install & run

Requires [uv](https://docs.astral.sh/uv/) and Python ≥ 3.11.

```bash
uv sync

uv run jdsl run examples/greeter.py                       # deterministic, no key
echo 'DEEPSEEK_API_KEY=sk-...' >> .env                    # or ANTHROPIC_API_KEY=...
uv run jdsl run examples/triage.py                        # LLM-driven
uv run pytest                                             # tests (no network)
```

The **provider is inferred from the model id**: `deepseek-chat` → DeepSeek,
`claude-*` → Anthropic, `gpt-*`/`o*` → OpenAI. A `.env` in the working directory
is loaded automatically.

## The API in one screen

| Combinator | Meaning |
| ---------- | ------- |
| `root(name, system=…)` | Entry point. Chain `.model(id)` then `.do(child)`. |
| `seq(*children)` | Run in order; fail fast (behavior-tree AND). |
| `sel(*children)` | Try until one succeeds (behavior-tree OR). |
| `repeat(child, until=…, max=n)` | Loop `child` until `until` succeeds or `max` passes (retry/refine). |
| `act(fn, *args)` | Leaf calling a `@tool`; literal args are type-checked. |
| `ref("key")` | An `act` argument resolved from the blackboard at run time. |
| `store(act(…), "key")` | Capture an action's return value onto the blackboard. |
| `check("key", value)` | Guard leaf: succeeds iff `blackboard["key"] == value`. |
| `predict("a -> b")` | DSPy-style LLM leaf: reads inputs, writes outputs. |

## Layout

```
jdsl/        the package — dsl, tree (interpreter), context, provider, router, config, cli
examples/    runnable skills — see examples/README.md
test/        pytest suite (no network; LLM leaves use fakes)
docs/        concepts, API reference, providers
```

## Docs

- [docs/concepts.md](docs/concepts.md) — behavior trees, the blackboard, signatures, why no codegen
- [docs/api.md](docs/api.md) — full combinator + node reference
- [docs/providers.md](docs/providers.md) — models, keys, `.env`, routing
- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, tests, adding examples

## Status

Work in progress. The interpreter, combinator API, signatures, and the
Anthropic / OpenAI-compatible (DeepSeek, OpenAI) backends run today. Not yet
built: Google provider, and the DSPy-defining **optimization** step (tuning
prompts against a metric) — the natural next direction now the runtime exists.

## License

Apache-2.0 · Author: Machar Kook
