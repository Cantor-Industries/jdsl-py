# jdsl host plugins

Thin host shims (design §29) that forward a frontier host's structured tool events
to the local jdsl harness ingest daemon for later compilation. The backend is
common; only the host wrapper differs.

## Prerequisites

Run the harness daemon so the forwarders have somewhere to post:

```bash
jdsl harness serve          # listens on http://127.0.0.1:8848 by default
```

Forwarders **fail open** (§7.2): if the daemon is not running, the hook still exits
0 with empty output and never blocks or fails a tool call. Capture is best-effort.

## Claude Code (`jdsl-claude-plugin/`)

Install the plugin directory into Claude Code (it declares hooks in
`hooks/hooks.json` and a forwarder in `scripts/`). The forwarder reads Claude's
structured JSON hook payload from stdin — never scraped terminal text — and posts
it to `/hook/claude` (§8.2, §29.1).

Environment:

| var | default | meaning |
|-----|---------|---------|
| `JDSL_INGEST_URL` | `http://127.0.0.1:8848` | ingest daemon base URL |
| `JDSL_CAPTURE_ID` | `cap_claude` | route events into a named capture |
| `JDSL_HOOK_TIMEOUT` | `0.5` | max seconds to wait on the hot path |

## Gemini CLI (`jdsl-gemini-extension/`)

Gemini exposes a broader hook surface, including model and tool-selection events
(§29.2). This extension registers the capture-only subset (`SessionStart`,
`BeforeToolSelection`, `BeforeTool`, `AfterTool`, `SessionEnd`) and posts to
`/hook/gemini`. Full model requests are not stored by default.

## Capture fidelity

An adapter never claims more than it sees (§8.2). Events carry their `source.host`
and `source.adapter`, and `jdsl capture inspect` reports the fidelity level (F0–F4,
§9) the evidence actually supports.
