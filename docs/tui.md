# Harness TUI

The TUI is the easiest way to operate a local capture and compilation session.
It is a dashboard over the existing harness APIs, not a second runtime.

## Start

After the curl install:

```bash
jdsl tui
```

From a checkout:

```bash
uv sync
uv run jdsl tui
```

The dashboard uses `JDSL_HARNESS_HOME` when set, otherwise it stores data under
`~/.local/share/jdsl-harness`.

## Capture Workflow

1. Select **Start server**. The dashboard displays the local ingest URL. If
	port `8848` is busy, it automatically selects an available port.
2. Select **New capture**. The generated capture id is placed in the form.
3. Set `JDSL_INGEST_URL` and `JDSL_CAPTURE_ID` in the host environment.
4. Install or enable the Claude Code, Gemini CLI, or OpenCode plugin.
5. Drive the host through successful task episodes.
6. Select **Inspect** to view episode, deterministic-candidate, and residual counts.
7. Select **Finish capture** when the capture is complete.
8. Select **Stop server** when the host is no longer sending events.
9. Select **Compile** to write the `.jdsl` package.

Host plugins remain separate because each host owns its own plugin format and
installation directory. The TUI shows the connection details but does not alter
the host's configuration implicitly.

## Controls

| Control | Purpose |
| --- | --- |
| Start server | Starts the loopback ingest server in the TUI process. |
| Stop server | Stops the loopback server. An active capture must be finished first. |
| New capture | Creates a capture through `CaptureCoordinator`. |
| Finish capture | Closes the selected capture. |
| Inspect | Runs the existing lineage report. |
| Compile | Builds, verifies, exports, and records a package. |
| `r` | Refreshes the capture list. |
| `q` | Exits and stops the local server. |

The TUI reports replay coverage and residual decision burden after compilation.
Those are evidence and structural metrics; held-out task evaluation is still
required before treating a package as generally correct.
