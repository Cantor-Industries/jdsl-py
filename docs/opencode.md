# OpenCode capture

jdsl captures OpenCode as a Tier-B host hook source. OpenCode remains an evidence
source; `.jdsl` packages still run through the jdsl package runtime.

## Requirements

- OpenCode installed and configured with your model provider.
- The jdsl harness daemon running locally.
- The project-local plugin from `plugins/jdsl-opencode-plugin/jdsl.ts`.

Development note: in this workspace, `opencode --version` returned `command not
found`, so the TypeScript plugin follows the official documented OpenCode hook
shape but still needs verification against your installed OpenCode type
declarations.

## Install the plugin

Project-local install:

```bash
mkdir -p .opencode/plugins
ln -sf ../../plugins/jdsl-opencode-plugin/jdsl.ts .opencode/plugins/jdsl.ts
```

Global install:

```bash
mkdir -p ~/.config/opencode/plugins
ln -sf "$(pwd)/plugins/jdsl-opencode-plugin/jdsl.ts" ~/.config/opencode/plugins/jdsl.ts
```

OpenCode loads plugins from `.opencode/plugins/` and
`~/.config/opencode/plugins/`.

## Start capture

```bash
export JDSL_HARNESS_HOME=/tmp/jdsl-opencode
export JDSL_CAPTURE_ID=cap_opencode
export JDSL_INGEST_URL=http://127.0.0.1:8848
export JDSL_HOOK_TIMEOUT=0.5

uv run jdsl harness serve
```

In another shell:

```bash
opencode
```

Drive a task that performs tool calls, then inspect the capture:

```bash
uv run jdsl capture list
uv run jdsl capture inspect cap_opencode
```

## What is recorded

The plugin forwards a stable `jdsl.opencode-hook.v1` envelope to:

```text
POST /hook/opencode?cap=<capture_id>
```

The Python adapter maps:

```text
session.created      -> episode.started
tool.execute.before  -> tool.call.started
tool.execute.after   -> tool.call.completed/tool.call.failed
session.error        -> annotation
session.deleted      -> episode.finished
```

Tool starts and completions are correlated by OpenCode `callID` when present.
The canonical trace stores that value as `host_call_id` and links completion
events with `parent_event_id`.

## Failure behavior

The plugin fails open. If the jdsl daemon is unavailable, slow, or rejects a
payload, OpenCode tool execution continues. The plugin emits at most one local
warning for transport failures.

## Compile

Once the capture contains enough successful episodes:

```bash
uv run jdsl compile cap_opencode \
  --name opencode-behavior \
  --out opencode-behavior.jdsl
```

Then inspect and run the package through jdsl:

```bash
uv run jdsl package inspect opencode-behavior.jdsl
uv run jdsl package run opencode-behavior.jdsl --tools <bindings.py> --input <input>=<value>
```

`<bindings.py>` must define `TOOLS = {logical_id: callable}` for every capability
shown by `package inspect`. The input names are the keys printed in the compile
report's `stats.inputs`; for example, if compile reports `"inputs": ["command"]`,
run with `--input command='...'`.

## Troubleshooting

If `capture list` is empty, confirm `JDSL_CAPTURE_ID`, `JDSL_INGEST_URL`, and
that `uv run jdsl harness serve` is still running.

If events lack parent linkage, inspect whether the plugin envelope includes
`call_id`. Without a host call id, jdsl marks correlation as inferred or
ambiguous.

If OpenCode does not load the plugin, verify the symlink target and run:

```bash
opencode --version
```

Then inspect the installed `@opencode-ai/plugin` type declarations and adjust
`plugins/jdsl-opencode-plugin/jdsl.ts` if your local hook shape differs.

## Uninstall

Project-local:

```bash
rm .opencode/plugins/jdsl.ts
```

Global:

```bash
rm ~/.config/opencode/plugins/jdsl.ts
```
