# jdsl

<p align="center">
  <img src="docs/for_respected_human.png" alt="jdsl logo" width="240" />
</p>

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

…and the model can drive **your** tools. A `react` leaf hands it your `@tool`s and
lets it pick and chain them (native function-calling):

```python
from jdsl import tool, root, react

@tool
def distance_km(origin: str, destination: str) -> int: ...   # your Python
@tool
def drive_hours(km: int) -> float: ...

skill = root("Trip").model("deepseek-chat").do(
    react("request -> answer", tools=[distance_km, drive_hours])
)
skill.run(request="Driving Nairobi to Mombasa — how long?")
```

```
 > distance_km(origin='Nairobi', destination='Mombasa') -> 485
 > drive_hours(km=485)                                  -> 6.1
answer: About 6.1 hours.
```

Triage steers the model with the tree; `react` lets the model steer your tools.
Full version: [examples/trip.py](examples/trip.py).

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
| `invert(child)` · `optional(child)` | Decorators: flip a status · fail-soft (a failing step won't abort its `seq`). |
| `timeout(child, seconds=…)` · `oneshot(child)` | Decorators: bound wall-clock time · run once per run, replay the status. |
| `act(fn, *args)` | Leaf calling a `@tool`; literal args are type-checked. |
| `ref("key")` | An `act` argument resolved from the blackboard at run time. |
| `store(act(…), "key")` | Capture an action's return value onto the blackboard. |
| `check("key", value)` | Guard leaf on `blackboard["key"]`; string matches are case/whitespace-lenient. |
| `predict("a -> b")` | DSPy-style LLM leaf: reads inputs, writes outputs. |
| `react("q -> a", tools=[…])` | Agentic leaf: the model calls `@tool`s in a loop (function-calling) until it answers. |

## Layout

```
jdsl/          the runtime core — dsl, tree (interpreter), context, provider, render, cli
  trace/       canonical trace events, sinks, storage, redaction, replay
  ir/          Behavior IR: schema, safe guard expressions, validation, lowering
  package/     .jdslpkg manifest, tool contracts, provenance, export + loader
jdsl_harness/  capture + behavior compiler (separate package; optional [harness] extra)
plugins/       Claude Code plugin + Gemini CLI extension (trace capture)
examples/      runnable skills — see examples/README.md
test/          pytest suite (no network; LLM leaves use fakes)
docs/          concepts, API reference, providers, harness & compiler
```

## Behavior harness & compiler

jdsl can also *compile* observed frontier-model behavior into portable policy a
smaller frozen model runs. The harness captures canonical traces, mines and
verifies reusable structure (exact dataflow, sequencing, guards, recovery), and
leaves only irreducible semantic decisions as typed signatures — exported as a
deterministic `.jdslpkg`.

```bash
jdsl harness serve                 # local capture daemon
jdsl capture inspect <id>          # exact-lineage report
jdsl compile <id> --out retail.jdslpkg
jdsl package run retail.jdslpkg --tools tools.py --model <small-model>
```

See [docs/harness.md](docs/harness.md) for the full design-to-code map.

## Docs

- [docs/concepts.md](docs/concepts.md) — behavior trees, the blackboard, signatures, why no codegen
- [docs/api.md](docs/api.md) — full combinator + node reference
- [docs/providers.md](docs/providers.md) — models, keys, `.env`, routing
- [docs/harness.md](docs/harness.md) — the capture harness and behavior compiler
- [docs/jdsl_behaviour_compiler.md](docs/jdsl_behaviour_compiler.md) — the full engineering design
- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, tests, adding examples

## Status

Work in progress. The interpreter, combinator API, signatures, and the
Anthropic / OpenAI-compatible (DeepSeek, OpenAI) backends run today. Not yet
built: Google provider, and the DSPy-defining **optimization** step (tuning
prompts against a metric) — the natural next direction now the runtime exists.

## License

O`Saasy · Author: Cantor Industries
