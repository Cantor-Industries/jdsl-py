# Examples

Each file is a single, runnable skill. Run one with:

```bash
uv run jdsl run examples/<name>.py            # or: uv run python examples/<name>.py
uv run jdsl run examples/<name>.py -i key=value   # seed blackboard inputs
```

| Example | Shows | Needs a key |
| ------- | ----- | ----------- |
| [greeter.py](greeter.py) | The smallest skill: `root → seq → act`. Deterministic. | no |
| [triage.py](triage.py) | The LLM drives a `selector`: `predict` classifies, `check` branches. | yes |
| [reason.py](reason.py) | Chain-of-thought: `predict` reasons, a second `predict` reads that reasoning to answer. | yes |
| [pipeline.py](pipeline.py) | Multi-step: multi-field signature, `check` routing, a second `predict` chained on the first. | yes |
| [refine.py](refine.py) | Iterative refinement with `repeat`: draft → critique → revise until `check("ok","yes")` passes. | yes |
| [wiki.py](wiki.py) | `ref` wiring across steps: search → model picks a title → fetch. | yes |

Deterministic examples (no `predict`) run without any key. LLM examples read a
key from `.env` (`DEEPSEEK_API_KEY` or `ANTHROPIC_API_KEY`) — see
[../docs/providers.md](../docs/providers.md).

New examples: follow the checklist in [../CONTRIBUTING.md](../CONTRIBUTING.md)
and add a row here.
