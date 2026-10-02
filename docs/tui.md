# JDSL TUI

The TUI currently focuses on authoring skills. It edits the restricted Behavior
IR used by `.jdsl` packages; harness capture and compilation remain available
through their separate CLI and APIs.

<p align="center">
	<img src="tui.png" alt="JDSL skill authoring TUI" width="960" />
</p>

The workbench keeps the tree visible on the left and the selected node's
properties on the right. The properties form scrolls independently on smaller
terminals.

## Start

Install the optional TUI dependency:

```bash
pip install 'jdsl[tui]'
jdsl tui
```

From a checkout:

```bash
uv sync
uv run --extra tui jdsl tui
```

## Author a Skill

Launching `jdsl tui` opens the skill editor directly. Select a node and
configure its properties, then add children from the node palette. The
editor supports sequence, selector, action, guard, predict, react, and repeat
nodes. Predict and react leaves expose their signature inputs, output,
instructions, model/provider hint, and react tool set.

Inspector changes apply after a short pause. **Validate** runs the same
structural checks used by the package loader. **Save** writes a portable package
and loads it again to verify the serialized artifact. **Open** loads a verified
package, and **New** starts a blank skill; both prompt before discarding dirty
edits. The output contains restricted IR and capability contracts, not arbitrary
Python code.

**Run** accepts a Python tools module defining `TOOLS` and an optional
`PREDICATES` mapping, plus comma-separated `key=value` inputs. The workbench
asks before importing a tools module and remembers approval by file path and
content hash. Runs execute in a worker, with progress and node status streamed
to the trace panel. Tool arguments and results are not printed in that log.

`Ctrl+S` saves, `Ctrl+O` opens, `Ctrl+N` creates a skill, `Ctrl+R` runs,
`Ctrl+Z` undoes, and `Ctrl+Shift+Z` redoes. `Ctrl+M` toggles reduced motion;
`Ctrl+G` switches ASCII-safe and Unicode node glyphs. Truecolor terminals are
recommended (`COLORTERM=truecolor`).

Harness capture and compilation remain available through the commands documented
in [Harness Usage](harness_usage.md). They are intentionally outside this TUI
while the skill authoring workflow is being developed.

The app, theme, settings, run panel, trust dialog, and workbench are grouped in
`jdsl/tui/`. `jdsl.tui_skill` remains as a compatibility import for older callers.
