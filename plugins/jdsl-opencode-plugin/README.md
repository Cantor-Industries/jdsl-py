# jdsl OpenCode plugin

Thin OpenCode hook forwarder for the jdsl harness.

It observes OpenCode session and tool hooks, converts them into the stable
`jdsl.opencode-hook.v1` envelope, and posts them to the local jdsl ingest daemon:

```bash
export JDSL_HARNESS_HOME=/tmp/jdsl-opencode
export JDSL_CAPTURE_ID=cap_opencode
export JDSL_INGEST_URL=http://127.0.0.1:8848
export JDSL_HOOK_TIMEOUT=0.5

uv run jdsl harness serve
```

Install project-locally during development:

```bash
mkdir -p .opencode/plugins
ln -sf ../../plugins/jdsl-opencode-plugin/jdsl.ts .opencode/plugins/jdsl.ts
opencode
```

Or install globally:

```bash
mkdir -p ~/.config/opencode/plugins
ln -sf "$(pwd)/plugins/jdsl-opencode-plugin/jdsl.ts" ~/.config/opencode/plugins/jdsl.ts
opencode
```

The plugin fails open. If the daemon is unavailable or slow, OpenCode tool
execution continues.

Development note: this repository shell could not run `opencode --version`
(`command not found`), so this plugin follows the official documented hook names
and fields but still needs verification against the locally installed OpenCode
type declarations before treating it as release-tested.
