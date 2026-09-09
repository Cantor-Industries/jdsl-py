# Repository Layout

jdsl is split into a small runtime and a separate harness/compiler layer.

```text
jdsl/
  dsl.py          authoring combinators
  tree.py         behavior-tree interpreter
  context.py      blackboard, context window, model turn types
  provider.py     model dispatch and tool-calling adapters
  config.py       key storage and model-id provider inference
  render.py       ASCII tree rendering
  trace/          canonical events, sinks, blobs, replay
  ir/             serializable Behavior IR and guard expressions
  package/        .jdsl manifest, export, load, bind

jdsl_harness/
  store.py        SQLite metadata plus append-only JSONL event spools
  capture.py      capture lifecycle and lineage report
  gateway.py      Tier-A tool wrapper
  mcp_proxy.py    MCP proxy recording
  server.py       loopback ingest HTTP server and optional MCP control plane
  adapters/       Claude Code, Gemini CLI, OpenCode, generic import
  compiler/       normalize, consolidate, staticize, residualize, verify, package
  metrics.py      package and experiment metrics
```

## Runtime Boundary

The core `jdsl` package should remain light. Heavy host integration and live MCP
dependencies belong in `jdsl_harness` or optional extras.

The public authoring API is exported from `jdsl/__init__.py`. Do not broaden it
unless a user should actually import the symbol.

## Test Shape

Tests live under `test/`, one file per module or behavior surface. Provider tests
use fake models; CI must not require network or real API keys.

Quality gate:

```bash
uv run pytest
uv run ruff check jdsl jdsl_harness examples test
```

Docs gate:

```bash
uv run --group docs mkdocs build --strict
```

## Runtime Flow by File

Read these in order when learning how authored skills run:

| Order | File | Why it matters |
| --- | --- | --- |
| 1 | `jdsl/dsl.py` | Turns `root`, `seq`, `act`, `predict`, and friends into node objects. |
| 2 | `jdsl/tree.py` | Executes the behavior tree. Every node implements `_tick`. |
| 3 | `jdsl/context.py` | Defines blackboard state, scoped system context, and model turn types. |
| 4 | `jdsl/provider.py` | Dispatches `predict`/`react` calls to Anthropic or OpenAI-compatible backends. |
| 5 | `jdsl/render.py` | Walks node children to print the tree shape. |

## Harness Flow by File

Read these in order when learning how traces become packages:

| Order | File | Why it matters |
| --- | --- | --- |
| 1 | `jdsl/trace/events.py` | Defines the host-neutral event envelope and event kinds. |
| 2 | `jdsl/trace/sink.py` | Assigns event sequence and hash-chain fields. |
| 3 | `jdsl_harness/store.py` | Persists captures as JSONL plus a SQLite index. |
| 4 | `jdsl_harness/capture.py` | Starts/finishes captures and emits lineage reports. |
| 5 | `jdsl_harness/compiler/normalize.py` | Converts events into normalized tool steps and decisions. |
| 6 | `jdsl_harness/compiler/consolidate.py` | Groups evidence into graded behavior candidates. |
| 7 | `jdsl_harness/compiler/staticize.py` | Emits deterministic Behavior IR plus residual signatures. |
| 8 | `jdsl_harness/compiler/verify.py` | Checks IR structure and replay coverage. |
| 9 | `jdsl_harness/compiler/package.py` | Builds the final `BehaviorPackage`. |
| 10 | `jdsl/package/load.py` | Loads, verifies, binds, and lowers a package to runtime nodes. |

## What to Keep Private

Long design notes, roadmap material, and notebooks belong in `docs/drafts/`.
That directory is ignored by Git and excluded from MkDocs. Public docs should
describe implemented behavior and link to tracked source-facing pages.
