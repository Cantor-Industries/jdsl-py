# CLI

The `jdsl` command covers runtime execution, provider config, capture,
compilation, and package execution.

## Runtime Commands

Render a skill without executing it:

```bash
uv run jdsl show examples/gate.py
```

Run every module-level `root(...)` skill in a file:

```bash
uv run jdsl run examples/greeter.py
uv run jdsl run examples/gate.py -i role=admin
```

Inputs use repeated `key=value` flags. Values arrive as strings unless your tool
or model leaf converts them.

## Provider Config

```bash
uv run jdsl config add -p deepseek sk-...
uv run jdsl config list
```

Stored keys live at `~/.local/share/recon/auth.json`. `config list` masks key
values before printing them.

## Harness Commands

Remove a curl-installed JDSL CLI while preserving captures and credentials:

```bash
jdsl uninstall
jdsl uninstall --yes
```

For older installations that do not have the command yet, use the installer
directly:

```bash
curl -fsSL https://cantorindustries.com/jdsl-py/install.sh | bash -s -- --uninstall
```

Open the interactive harness dashboard:

```bash
jdsl tui
```

The dashboard starts the local server, creates captures, inspects lineage, and
compiles packages. See [Harness TUI](tui.md) for the host-plugin handoff.

Run the local ingest server:

```bash
jdsl harness serve
```

List and inspect captures:

```bash
jdsl capture list
jdsl capture inspect cap_retail
```

Import generic JSONL traces:

```bash
jdsl capture import runs.jsonl --capture cap_imported
```

Compile:

```bash
jdsl compile cap_imported --name retail --out retail.jdsl
```

## Package Commands

Inspect package metadata and declared effects:

```bash
uv run jdsl package inspect retail.jdsl
```

Verify package structure and file digests:

```bash
uv run jdsl package verify retail.jdsl
```

Run a package against trusted host tools:

```bash
uv run jdsl package run retail.jdsl --tools tools.py \
  -i email=ada@example.com \
  -i request="cancel my order"
```

Use `--model <model-id>` when the package contains residual model leaves.

## Exit Behavior

Invalid config, missing skills, malformed inputs, missing tool bindings, invalid
packages, and failed verification exit non-zero. Runtime tool exceptions
propagate unless you encode recoverable failure as `Status.FAILURE` and handle it
with a selector.
