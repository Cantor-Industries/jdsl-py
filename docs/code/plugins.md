# Host Plugins

Host plugins live under
[`plugins/`](https://github.com/Cantor-Industries/jdsl-py/tree/harness/plugins).
They are capture shims. They do not run `.jdsl` packages and they are not needed
by the package runtime.

The shared pattern is:

```text
host hook payload
  -> small plugin/forwarder
  -> POST http://127.0.0.1:8848/hook/<host>?cap=<capture_id>
  -> host adapter
  -> canonical TraceEvent
  -> HarnessStore
```

The local ingest server is implemented in
[`jdsl_harness/server.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/server.py).
It returns HTTP 200 with `{ "ok": false }` for malformed hook payloads so capture
does not break the host agent session.

## Correlation

Many hosts send "before tool" and "after tool" as separate hook calls.
[`adapters/correlation.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/adapters/correlation.py)
keeps short-lived in-memory state so completion events can point back to the
started event with `parent_event_id`.

The correlator prefers a host-provided call id from fields such as `call_id`,
`tool_call_id`, `tool_use_id`, `invocation_id`, or `id`. If the host gives no id,
it can infer a link only when exactly one open call is compatible. Otherwise the
event is marked as ambiguous rather than pretending the linkage is exact.

## Claude Code

The Claude Code shim is under
[`plugins/jdsl-claude-plugin/`](https://github.com/Cantor-Industries/jdsl-py/tree/harness/plugins/jdsl-claude-plugin).
Its Python forwarder posts hook payloads to `/hook/claude`.

[`claude_code.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/adapters/claude_code.py)
maps structured hook names into trace events:

| Claude hook | jdsl event |
| --- | --- |
| `SessionStart` | `episode.started` |
| `UserPromptSubmit` | `user.message` |
| `PreToolUse` | `tool.call.started` |
| `PostToolUse` | `tool.call.completed` |
| `PostToolUseFailure`, `PostToolBatchFailure` | `tool.call.failed` |
| `SubagentStart`, `SubagentStop` | host subagent events |
| `SessionEnd` | `episode.finished` |

Claude tool results may arrive wrapped as MCP content blocks. The adapter tries
to recover structured JSON from `structuredContent`, content-block arrays, or
JSON-looking strings so lineage sees fields such as `id`, not only opaque text.

## Gemini CLI

The Gemini CLI extension is under
[`plugins/jdsl-gemini-extension/`](https://github.com/Cantor-Industries/jdsl-py/tree/harness/plugins/jdsl-gemini-extension).
It posts to `/hook/gemini`.

[`gemini_cli.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/adapters/gemini_cli.py)
maps:

| Gemini hook | jdsl event |
| --- | --- |
| `SessionStart` | `episode.started` |
| `BeforeToolSelection` | `toolset.exposed` |
| `BeforeTool` | `tool.call.started` |
| `AfterTool` | `tool.call.completed` or `tool.call.failed` |
| `SessionEnd` | `episode.finished` |

Gemini exposes more hook surface than the current jdsl adapter uses. The current
implementation is capture-oriented; enforcement and tool filtering are not part
of the shipped path.

## OpenCode

The OpenCode plugin is under
[`plugins/jdsl-opencode-plugin/`](https://github.com/Cantor-Industries/jdsl-py/tree/harness/plugins/jdsl-opencode-plugin).
Its TypeScript entry point creates a stable jdsl envelope with schema
`jdsl.opencode-hook.v1`.

[`opencode.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/adapters/opencode.py)
validates the envelope before emitting events. Tool envelopes must include a
tool name, before hooks must include `args`, and after hooks must include either
`result` or `error`.

| OpenCode hook | jdsl event |
| --- | --- |
| `session.created` | `episode.started` |
| `tool.execute.before` | `tool.call.started` |
| `tool.execute.after` | `tool.call.completed` or `tool.call.failed` |
| `session.error` | `annotation` |
| `session.finished`, `session.ended`, `session.deleted` | `episode.finished` |
| idle/status/compaction hooks | `annotation` |

The adapter keeps workspace metadata such as `directory` and `worktree` in the
payload because those fields matter when compiling coding-agent behavior.

## MCP Proxy

[`jdsl_harness/mcp_proxy.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/mcp_proxy.py)
is Tier-A capture for MCP-native tools.

Instead of relying on a host-wide hook, jdsl can proxy an upstream MCP server:

1. discover upstream tools
2. expose namespaced copies such as `mcp__retail__get_order`
3. preserve input/output schemas
4. forward calls to the upstream server
5. record canonical started/completed/failed events

The package compiler treats the logical id as `server.tool`, while the host sees
the namespaced MCP tool name. This keeps tools from different MCP servers from
colliding.

The MCP SDK is optional. Transport code imports it lazily; the recording helpers
and tests can run without it.

## What Plugins Can Prove

Capture fidelity depends on the host:

| Capture path | What the compiler can usually trust |
| --- | --- |
| jdsl runtime tracing | Tree nodes, model requests/responses, tool calls, blackboard writes. |
| ToolGateway | Tool identity, arguments, results, errors, optional state snapshots. |
| MCP proxy | Routed MCP tool schemas, arguments, and results. |
| Claude/Gemini/OpenCode hooks | The subset of host events exposed by that hook API. |
| imported JSONL | Only the fields present in the imported records. |

The adapters should never claim full behavior visibility when they only saw a
routed subset of tool calls.
