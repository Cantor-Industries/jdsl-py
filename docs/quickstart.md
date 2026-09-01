# Quickstart

This page gets you from a fresh checkout to a running skill.

## Install

jdsl uses Python 3.11 or newer and `uv`.

```bash
uv sync
uv run pytest
```

The test suite is offline. Provider calls are faked in tests.

## Run a Deterministic Skill

`examples/greeter.py` has no model leaves, so it needs no API key.

```bash
uv run jdsl show examples/greeter.py
uv run jdsl run examples/greeter.py
```

`show` renders the tree without executing it. `run` imports every module-level
`root(...)` skill in the file and executes it.

## Seed Inputs

Inputs become blackboard keys for that run.

```bash
uv run jdsl run examples/gate.py -i role=admin
uv run jdsl run examples/gate.py -i role=guest
uv run jdsl run examples/gate.py -i role=banned
```

Inside a tree, `ref("role")` resolves from the same blackboard. Missing refs
raise with a message telling you to seed the key or produce it earlier.

## Run an LLM-Backed Skill

Set a key for the provider implied by your model id:

```bash
echo 'DEEPSEEK_API_KEY=sk-...' >> .env
uv run jdsl run examples/triage.py
```

The skill uses `predict("message -> category")`. The model writes `category`,
then normal tree guards decide which action runs.

## Write the Smallest Skill

```python
from jdsl import act, root, seq, store, tool

@tool
def greet(name: str) -> str:
    return f"hello {name}"

skill = root("Greeter").do(seq(store(act(greet, "Ada"), "message")))

ctx = skill.run()
print(ctx.blackboard["message"])
```

Use [Concepts](concepts.md) next if the blackboard and status rules are new.
Use [API Reference](api.md) when you need exact combinator behavior.
