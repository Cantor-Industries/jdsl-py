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
