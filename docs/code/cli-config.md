# CLI and Providers

The CLI lives in
[`jdsl/cli.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/cli.py).
It exposes the runtime and harness without making the core runtime depend on the
harness extra at import time.

## Command Groups

| Command | Implementation path | Purpose |
| --- | --- | --- |
| `jdsl config ...` | `config_app` in `jdsl/cli.py` | Store and list provider API keys. |
| `jdsl run FILE.py` | `run()` in `jdsl/cli.py` | Import a Python file and run every module-level `Root`. |
| `jdsl show FILE.py` | `show()` in `jdsl/cli.py` | Render behavior trees without executing them. |
| `jdsl capture ...` | lazy imports from `jdsl_harness` | List, import, and inspect trace captures. |
| `jdsl compile ...` | `compile_behavior` | Compile a capture into a `.jdsl` package. |
| `jdsl package ...` | `jdsl.package` | Inspect, verify, and run compiled packages. |
| `jdsl harness serve` | `IngestServer` | Start the local loopback capture daemon. |

Runtime commands import only `jdsl`. Harness commands import `jdsl_harness`
inside the command function, so a dependency-light install can still run authored
skills.

## Running Python Skills

`jdsl run examples/triage.py` imports the file with
`importlib.util.spec_from_file_location`, then scans module globals for `Root`
instances.

Each root is executed with the same parsed `--input key=value` seed values:

```bash
uv run jdsl run examples/triage.py -i message="I was double charged"
```

Input parsing is intentionally simple: CLI inputs are strings. Richer values can
be passed programmatically through `skill.run(**inputs)`.

After a run, the CLI prints the blackboard and warns about blackboard clobbers.
A clobber is a write where one node overwrote a key last written by another
writer.

## Showing Trees

`jdsl show` uses
[`jdsl/render.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/render.py)
to display the tree shape. It does not call tools or models.

This is useful before running an LLM-backed skill:

```bash
uv run jdsl show examples/triage.py
```

## Provider Inference

Provider configuration lives in
[`jdsl/config.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/config.py)
and
[`jdsl/provider.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/provider.py).

`provider_for_model(model_id)` uses model-name prefixes:

| Prefix | Provider |
| --- | --- |
| `claude...` | Anthropic |
| `deepseek...` | DeepSeek |
| `gpt...`, `o1...`, `o3...`, `o4...` | OpenAI |
| `gemini...` | Google |
| unknown | Anthropic fallback |

DeepSeek and OpenAI use the OpenAI-compatible client path. Anthropic uses the
Anthropic SDK path. Google is recognized by config but the provider backend is
not implemented in the current runtime.

## Credentials

`config.py` loads `.env` on import and can also read stored keys from:

```text
~/.local/share/recon/auth.json
```

The environment variable names are:

| Provider | Env var |
| --- | --- |
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| Google | `GOOGLE_API_KEY` |

`jdsl config add -p deepseek <key>` merges keys into the stored config and
deduplicates them.

## Key Rotation

[`jdsl/router.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/router.py)
implements `RoundRobinRouter`.

`LanguageModel.generate` and `LanguageModel.converse` ask the router for the
current key. On authentication, permission, or rate-limit errors, the model layer
rotates to the next key and retries up to five attempts.

This is provider-level rotation, not per-model health tracking. `SmartRouter` is
currently an alias of `RoundRobinRouter`.

## Package Commands

`jdsl package run` loads a `.jdsl` archive or package directory, imports a Python
bindings file, reads a `TOOLS` dict and optional `PREDICATES` dict, then lowers
the Behavior IR into runtime nodes.

The important boundary is this:

```text
package names logical capabilities
host bindings provide Python callables
lowering connects them before execution
```

If a required capability is missing, `load_package(...).as_root(...)` fails
before the behavior tree runs.
