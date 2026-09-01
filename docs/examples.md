# Examples

Every script under `examples/` is a runnable skill. Start with deterministic
examples, then move to model leaves, then tool-using `react` leaves.

```bash
uv run jdsl run examples/<name>.py
uv run jdsl run examples/<name>.py -i key=value
```

| Example | What it teaches | Needs a key |
| --- | --- | --- |
| `greeter.py` | Minimum tree: `root -> seq -> act`. | no |
| `gate.py` | `optional` and `invert` decorators with deterministic access control. | no |
| `triage.py` | `predict` writes a category and `sel` branches on it. | yes |
| `pipeline.py` | Multi-output `predict`, guarded routing, then a second `predict`. | yes |
| `reason.py` | Two `predict` leaves: reasoning first, final answer second. | yes |
| `refine.py` | `repeat` loops critique and revision until a guard passes. | yes |
| `react.py` | Model-driven tool calling with native function calls. | yes |
| `trip.py` | A compact `react` example for chained calculations. | yes |
| `shop.py` | Tool-heavy ordering flow with search, comparison, and arithmetic. | yes |
| `db.py` | Schema discovery and array arguments in `react`. | yes |
| `wiki.py` | Search, model selection, and later tool call wired by `ref`. | yes |

## Choosing an Example

Use `greeter.py` or `gate.py` when you are learning tree semantics. Use
`triage.py` when you want to see a model make a local decision that deterministic
tree code consumes. Use `trip.py`, `shop.py`, or `db.py` when the model should
choose and chain tools inside one leaf.

Harness examples live under `examples/harness/`:

| File | Purpose |
| --- | --- |
| `retail_mcp_server.py` | A tiny MCP server that produces structured retail traces. |
| `retail_tools.py` | Host-tool bindings for running the sample compiled package. |
| `retail.jdsl` | A compiled behavior-package fixture. |

The harness fixture is intentionally structured: customer and order ids are
discrete fields, so the compiler can prove exact value flow instead of scraping
text.
