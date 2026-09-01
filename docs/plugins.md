# Plugins and Host Capture

Host plugins are thin shims. They forward structured host hook payloads to the
local harness ingest server so the compiler can later analyze the trace.

They are capture tools, not execution dependencies for `.jdsl` packages.

## Common Flow

Start the ingest daemon:

```bash
uv run jdsl harness serve
```

Set capture environment:

```bash
export JDSL_INGEST_URL=http://127.0.0.1:8848
export JDSL_CAPTURE_ID=cap_host
export JDSL_HOOK_TIMEOUT=0.5
```

Run the host with the plugin installed. After the session:

```bash
uv run jdsl capture list
uv run jdsl capture inspect cap_host
```

## Failure Policy

Plugins fail open. If the daemon is down, slow, or rejects a malformed payload,
the host tool call should continue. Capture must not break the user’s agent
session.

## Claude Code

The Claude Code shim lives under `plugins/jdsl-claude-plugin/`.

It forwards Claude hook payloads such as pre-tool and post-tool events to:

```text
POST /hook/claude?cap=<capture_id>
```

The adapter maps host tool names, inputs, responses, and call ids into canonical
trace events. It preserves structured MCP results where possible so lineage can
see fields instead of opaque text.

## Gemini CLI

The Gemini CLI extension lives under `plugins/jdsl-gemini-extension/`.

It forwards structured hook events to:

```text
POST /hook/gemini?cap=<capture_id>
```

Gemini exposes model and tool-selection hook surfaces. The current jdsl shim is
capture-oriented; enforcement and tool filtering are future work.

## OpenCode

The OpenCode plugin lives under `plugins/jdsl-opencode-plugin/`.

It forwards the stable `jdsl.opencode-hook.v1` envelope to:

```text
POST /hook/opencode?cap=<capture_id>
```

See [OpenCode Capture](opencode.md) for install and smoke-test steps.

## Correlation

When a host supplies a stable call id, adapters store it as `host_call_id` and
link completion events to started events with `parent_event_id`.

If a host omits call ids, the correlator may infer a link only when one pending
call is unambiguous. Otherwise the event is marked with lower correlation
fidelity rather than pretending the evidence is exact.

## Capture Fidelity

Host hooks usually provide tool-call visibility but not private model reasoning.
That is enough for many dataflow claims, but not enough to prove everything. The
lineage report and package manifest should reflect the fidelity the events
actually support.
