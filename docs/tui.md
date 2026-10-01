# JDSL TUI

The TUI currently focuses on authoring skills. It edits the restricted Behavior
IR used by `.jdsl` packages; harness capture and compilation remain available
through their separate CLI and APIs.

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

## Author a Skill

Launching `jdsl tui` opens the skill editor directly. Select a node and
configure its properties, then add children from the node palette. The
editor supports sequence, selector, action, guard, predict, react, and repeat
nodes. Predict and react leaves expose their signature inputs, output,
instructions, model/provider hint, and react tool set.

**Validate** runs the same structural checks used by the package loader.
**Save .jdsl** writes a portable package and loads it again to verify the
serialized artifact. The output contains restricted IR and capability contracts,
not arbitrary Python code.

The optional **Run** action accepts a Python tools module defining `TOOLS` and
an optional `PREDICATES` mapping, plus comma-separated `key=value` inputs. Runs
use the normal package binding/runtime path and capture node exit statuses in
memory; `[ok]` and `[!!]` markers show successful and failed nodes in the tree.

Harness capture and compilation remain available through the commands documented
in [Harness Usage](harness_usage.md). They are intentionally outside this TUI
while the skill authoring workflow is being developed.

The authoring shell is implemented in `jdsl/tui.py`; the tree editor and
package workbench live in `jdsl/tui_skill.py`.
