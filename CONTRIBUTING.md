# Contributing

## Setup

```bash
uv sync            # installs jdsl (editable) + dev tools
uv run pytest      # run the suite
uv run ruff check jdsl examples test
```

Python ≥ 3.11, [uv](https://docs.astral.sh/uv/) for everything.

## Style

Terse and dense, in the spirit of tinygrad — small files, one concept each, no
ceremony. Specifics:

- **Line length 120**, 4-space indent (ruff enforces both).
- Absolute imports only (`from jdsl.tree import ...`).
- Docstrings explain *why*, not *what the code obviously does*.
- Prefer a plain function to a class; prefer a combinator to a config object.
- Keep the public surface (`jdsl/__init__.py`) small and obvious.

Run `uv run ruff check jdsl examples test` before opening a PR; CI expects it
clean.

## Tests are required

Every PR that changes behavior needs tests, and the suite must stay **fast and
offline** — no network, no real API keys.

- Tests live in `test/`, one file per module (`test_tree.py`, `test_dsl.py`, …).
- The LLM is never called for real. Use the `fake_model` fixture (see
  `test/conftest.py`): a `LanguageModel`-shaped stub whose replies you script,
  and which records every call so you can assert on the prompt/system/model.
- Cover the branch you touched: a happy path *and* a failure path. Behavior-tree
  nodes have two outcomes (`SUCCESS`/`FAILURE`) — test both.

```bash
uv run pytest -q            # all
uv run pytest test/test_dsl.py -q
```

## Adding an example

Examples are teaching material and must run as-is.

1. Put a single-file script in `examples/`, named for what it demonstrates.
2. Start with a module docstring: what it shows, and the exact `uv run jdsl run
   examples/greeter.py` command (with any `-i key=value` inputs).
3. Deterministic examples need no key; LLM examples read one from `.env`.
4. Add a one-line entry to `examples/README.md`.
5. Keep external-service calls robust (timeouts, a descriptive User-Agent) — an
   example that crashes on a flaky network teaches nothing.

## Scope of a good PR

One idea per PR. New node type, new provider, new example, or a bug fix — not
all four. If you're adding a node, it needs: the node in `jdsl/tree.py`, a
combinator in `jdsl/dsl.py`, an export in `jdsl/__init__.py`, a row in
`docs/api.md`, and tests.
