# jdsl Harness: Next Implementation Steps

Implementation plan for coding agents working on the `harness` branch.

Research snapshot: 2026-08-30

Branch reviewed: `harness`

Primary goal:

> Make the jdsl harness reliable enough to capture behavior from frontier-agent hosts, compile portable `.jdslpkg` artifacts, and prove that packages with residual decision burden above zero improve smaller frozen models such as Gemma by moving procedure out of model context and into executable policy.

This document is intentionally implementation-focused. It assumes the current harness/compiler is real and working. The next work should harden what exists, fill the remaining execution gaps, add OpenCode as a first-class capture host, make residual signatures fully honored at runtime, add a supported model-binding path, and build the evaluation layer needed to compare `.jdslpkg` against Agent Skills and fine-tuning.

---

## 1. Read this before changing code

Coding agents should not start by designing a new architecture.

First inspect the current branch.

Required reading order:

```text
CONTRIBUTING.md
README.md

docs/harness.md
docs/harness_usage.md
docs/jdsl_behaviour_compiler.md

jdsl/context.py
jdsl/tree.py
jdsl/provider.py
jdsl/config.py

jdsl/trace/
jdsl/ir/
jdsl/package/

jdsl_harness/capture.py
jdsl_harness/store.py
jdsl_harness/server.py
jdsl_harness/gateway.py
jdsl_harness/mcp_proxy.py
jdsl_harness/metrics.py

jdsl_harness/adapters/
jdsl_harness/compiler/

plugins/

test/conftest.py
test/test_trace.py
test/test_ir.py
test/test_package.py
test/test_harness.py
test/test_compiler.py
test/test_server_cli.py
```

Before every implementation PR, run the current branch unchanged:

```bash
uv sync
uv sync --extra harness

uv run pytest
uv run ruff check jdsl jdsl_harness examples test
```

If the current documented lint command only names `jdsl examples test`, update the repository quality gate so `jdsl_harness` is included too.

Do not begin a feature on top of a failing baseline.

Record the baseline commit SHA in experiment artifacts and docs.

---

## 2. Preserve the repository's existing style

The current repository deliberately favors small, direct modules.

Follow the existing `CONTRIBUTING.md` rules.

Important constraints:

- Keep files small.
- Keep one concept per module.
- Prefer a function over a framework class where state is not required.
- Prefer the existing combinators and data types over new configuration systems.
- Use absolute imports.
- Keep line length at 120.
- Keep the core `jdsl` package dependency-light.
- Put heavy or host-specific dependencies in `jdsl_harness` or optional extras.
- Keep tests offline.
- Never require a real API key in CI.
- Use fake models and fixture payloads for provider/host tests.
- Add a failure-path test with each behavior change.
- Keep one main idea per PR.
- Update the relevant docs in the same PR as the behavior change.
- Do not broaden `jdsl/__init__.py` unless the public API truly needs a new symbol.

Avoid introducing:

- a new agent framework,
- a second tree runtime,
- a second trace format,
- arbitrary code inside `.jdslpkg`,
- a giant generic "plugin abstraction" before three hosts need the same abstraction,
- hidden network dependencies in core tests,
- model-specific behavior inside Behavior IR.

The harness branch already contains the architecture. Extend it.

---

## 3. What exists now

The current `harness` branch already implements most of the first compiler design.

### 3.1 Working today

The branch already has:

```text
jdsl/trace/
    canonical events
    sinks
    JSONL storage
    redaction/replay support

jdsl/ir/
    Behavior IR
    safe guard expressions
    validation
    lowering into runtime nodes

jdsl/package/
    manifests
    contracts
    provenance
    deterministic .jdslpkg export
    package loading and verification

jdsl_harness/
    SQLite/store layer
    capture coordinator
    Tier-A gateway
    transport-neutral MCP proxy recording
    loopback ingest server
    environment adapters
    compiler pipeline
    package metrics

plugins/
    Claude Code shim
    Gemini CLI shim
```

The compiler pipeline already follows:

```text
trace
-> normalize
-> lineage
-> candidates
-> consolidate
-> staticize
-> residualize
-> verify
-> package
```

The package loader already verifies structure and digests before binding trusted host tools.

The IR already supports dynamic references such as:

```text
orders[$selected_index].id
```

This is important.

A residual model leaf can produce only:

```text
selected_index = 1
```

Then deterministic runtime dataflow can resolve the exact order ID without asking the model to copy it.

### 3.2 RDB greater than zero already works in tests

Do not rebuild this mechanism.

`test/test_compiler.py` already contains a true end-to-end residual package test.

The test:

1. captures a teacher behavior with a semantic `selected_index` decision,
2. compiles a package,
3. verifies that one model-dependent decision remains,
4. exports and reloads the `.jdslpkg`,
5. runs it with a frozen fake small model,
6. uses the model-produced index to drive later deterministic refs,
7. runs the same package with a second frozen fake model.

This is the correct architecture.

The missing work is to promote this tested mechanism into:

- complete residual-signature runtime semantics,
- a real local-model adapter,
- a user-facing example,
- runtime telemetry,
- OpenCode capture,
- and comparative evaluation.

### 3.3 Important current gaps

The following gaps should drive the next PRs.

#### Gap A: `Predict` trace fidelity is below `React`

`React` emits explicit model-request and model-response events.

`Predict` currently performs a model call but does not emit equivalent high-fidelity model telemetry.

This blocks accurate measurement of:

- model call count,
- per-signature latency,
- actual input/output size,
- residual decision examples,
- model work fraction.

Fix this before building the evaluation layer.

#### Gap B: Behavior signatures contain fields the runtime does not fully honor

Behavior IR signatures already contain concepts such as:

- `inputs`,
- `output`,
- `instruction`,
- `examples`,
- `tools`,
- `context_policy`,
- `validator`.

Current lowering mainly carries the input/output names, schema, instruction, and tool list into runtime nodes.

Do not claim that a small model "uses the full compiled signature" until the runtime honors the fields the package exposes.

Either implement a field or remove/deprecate the field.

Unused package semantics are dangerous because package authors will assume they are enforced.

#### Gap C: live MCP proxy transport is unfinished

The transport-neutral `MCPProxy` recording layer exists.

The live proxy serving path still needs to be wired.

Tier A is the preferred capture mode because it gives the harness the strongest action visibility.

A real transparent MCP proxy is therefore core work, not polish.

#### Gap D: compiler-model implementation is narrower than the design language implies

The compiler model abstraction exists.

The offline heuristic implementation is useful.

The current LLM compiler path still falls back to heuristics for some proposal operations.

Keep docs exact about what is deterministic, what is heuristic, and what is genuinely model-proposed.

Do not market a compiler-model capability before the code performs it.

#### Gap E: package metrics are mostly static

Current metrics derive structural quantities from IR.

That is useful for:

- RDB,
- deterministic coverage,
- tool branching,
- exact-dataflow rate.

The current "active policy tokens" approximation is based on simple instruction splitting, so it should not be presented as true tokenizer-measured tokens.

Runtime evaluation needs actual telemetry.

#### Gap F: there is no first-class OpenCode adapter/plugin

Claude Code and Gemini are present.

OpenCode is a strong next host because:

- it supports plugins,
- it exposes tool execution hooks,
- it supports Agent Skills,
- the same host can later run a real Skill baseline for jdsl-versus-Skills experiments.

#### Gap G: there is no supported Hugging Face model path in package CLI

Programmatic model injection already works because the runtime accepts a model object.

A model ID such as:

```text
google/gemma-4-E2B-it
```

should not be assumed to work through the current provider-ID router as a Hugging Face model.

The repository needs an explicit model-object integration path.

Do not overload cloud-provider model IDs with Hugging Face execution semantics.

For current development, do not require Gemma to run on the local workstation.
The machine is GPU-constrained. Gemma experiments should run as manual GPU
integration work in Colab or an equivalent GPU host, using
`docs/gemma_colab_experiment.ipynb`. Local CI and local development should keep
using fake/spy models or tiny smoke-test models.

---

# Part I: harden the current runtime and trace path

## 4. PR 1: make the quality gate cover the harness

Goal:

Make every later coding-agent change run against the full branch rather than only the original runtime package.

### Changes

Update documented lint/test commands to cover:

```text
jdsl
jdsl_harness
examples
test
```

Preferred commands:

```bash
uv run pytest
uv run ruff check jdsl jdsl_harness examples test
```

If CI exists, make the same command authoritative there.

Do not introduce formatting rewrites unrelated to the current PR.

### Tests

No behavior tests required beyond existing full suite.

### Docs

Update:

```text
CONTRIBUTING.md
docs/harness.md
```

only if their commands are stale.

### Acceptance criteria

```text
pytest green
ruff green over jdsl_harness
no unrelated source reformat
```

---

## 5. PR 2: bring `Predict` tracing to parity with `React`

Goal:

Every residual model decision should be observable through the canonical trace.

### Current problem

A compiled package with:

```text
predict(request, orders -> selected_index)
```

contains a real model inference step.

The harness needs to know exactly when that step occurs.

### Required events

At minimum emit:

```text
model.requested
model.responded
```

from `Predict`.

The event payload should include:

```text
node_id
signature or signature_id if available
input field names
output field name
model identity when known
elapsed time
```

Capture mode determines whether actual input/output values are persisted.

Do not store hidden reasoning.

### Recommended request payload

Conceptually:

```json
{
  "node_id": "resolve_target",
  "kind": "predict",
  "inputs": {
    "request": "...",
    "orders": [...]
  },
  "output": {
    "name": "selected_index",
    "schema": {
      "type": "integer"
    }
  }
}
```

If redaction policy removes values, retain:

```text
field names
types
hashes
sizes
```

### Recommended response payload

```json
{
  "node_id": "resolve_target",
  "kind": "predict",
  "raw_output": "1",
  "parsed_output": 1,
  "elapsed_ms": 18.2
}
```

Store raw model text only where capture policy permits.

The canonical semantic value is the parsed output.

### Why this matters

This one PR unlocks:

- real RDB execution traces,
- residual examples,
- actual model-call metrics,
- latency attribution,
- model-output failure analysis,
- package versus Skill comparison.

### Tests

Add offline tests asserting:

- `Predict` emits one request and one response event.
- `node_id` matches the runtime node.
- parsed output is represented.
- a failed model call produces a trace failure path.
- trace sink failure behavior remains consistent with current runtime policy.
- RDB 0 packages emit zero model events.

### Docs

Update the trace event reference.

Add one example event to `docs/harness_usage.md`.

---

## 6. PR 3: add robust host tool-call correlation

Goal:

Stop relying on sequential proximity when multiple host tool calls overlap.

### Problem

Host hook integrations often emit:

```text
before tool
after tool
```

as separate host events.

If tool calls become concurrent, "the previous start event" is not a safe correlation mechanism.

### Add a host call identity

Normalize each host event into:

```text
host_call_id
```

where the host provides one.

If the host does not provide one:

- create an adapter-local correlation ID,
- keep it scoped to the host session,
- mark fidelity lower if correlation is inferred.

The canonical trace should let a completion refer to the correct call start.

### Storage

Maintain a short-lived mapping:

```text
(capture_id, episode_id, host_call_id)
-> canonical tool.call.started event_id
```

Then set:

```text
parent_event_id
```

on completion/failure events.

### Apply across all hosts

Do not build this only for OpenCode.

Update:

```text
Claude adapter
Gemini adapter
OpenCode adapter
generic MCP adapter
```

where host data permits.

### Tests

Fixture cases:

```text
A starts
B starts
B finishes
A finishes
```

Both completions must resolve to the correct parent.

Also test:

- missing completion,
- duplicate completion,
- missing host call ID,
- adapter restart.

---

# Part II: add OpenCode as a first-class capture host

## 7. Why OpenCode should be added now

OpenCode is useful for two different experiments.

### Experiment role 1: frontier capture

A strong model running inside OpenCode performs tasks.

The jdsl plugin records observable behavior.

Those traces compile into `.jdslpkg`.

### Experiment role 2: Agent Skills baseline

OpenCode supports Agent Skills.

That makes it a useful environment for later comparisons:

```text
same host
same model
same tools

SKILL.md
vs
jdsl package
```

Keep these roles distinct.

The OpenCode plugin is a capture integration.

The jdsl package runtime remains the primary executor for compiled packages.

Do not make an OpenCode "run package" wrapper the only execution path.

---

## 8. PR 4: add `jdsl_harness/adapters/opencode.py`

Goal:

Map one stable jdsl-defined OpenCode envelope into canonical trace events.

Do not make Python code depend directly on every detail of the OpenCode TypeScript API.

The TypeScript plugin should translate OpenCode events into a small jdsl envelope.

Then Python maps that envelope into the canonical event schema.

### First inspect the installed OpenCode version

The coding agent should run:

```bash
opencode --version
```

Then inspect the installed `@opencode-ai/plugin` type declarations.

Do not guess hook input fields from an old blog post or a different OpenCode release.

The stable public docs currently describe plugins loaded from:

```text
.opencode/plugins/
~/.config/opencode/plugins/
```

and hooks including tool execution and session events.

Use the installed type definitions as the final source for the exact local version.

### Stable jdsl envelope

Example shape:

```json
{
  "schema": "jdsl.opencode-hook.v1",
  "hook": "tool.execute.before",
  "session_id": "ses_...",
  "call_id": "call_...",
  "tool": "read",
  "args": {
    "filePath": "..."
  },
  "directory": "...",
  "worktree": "...",
  "timestamp": "..."
}
```

Completion:

```json
{
  "schema": "jdsl.opencode-hook.v1",
  "hook": "tool.execute.after",
  "session_id": "ses_...",
  "call_id": "call_...",
  "tool": "read",
  "result": "...",
  "error": null,
  "timestamp": "..."
}
```

Session envelope:

```json
{
  "schema": "jdsl.opencode-hook.v1",
  "hook": "session.created",
  "session_id": "ses_...",
  "timestamp": "..."
}
```

### Episode mapping

Default:

```text
OpenCode session_id -> jdsl episode_id
```

Allow explicit episode override later.

### Adapter output

Map:

```text
session.created -> episode.started
tool.execute.before -> tool.call.started
tool.execute.after -> tool.call.completed
session.error -> annotation or episode failure evidence
session.idle/end -> episode boundary candidate
```

Do not end an episode on every idle event unless tests prove that matches the intended capture semantics.

### Tests

Use static fixture JSON.

No OpenCode process in CI.

Test:

- session creation,
- before tool,
- after tool,
- failure,
- unknown event,
- malformed payload,
- correlation.

---

## 9. PR 5: add the OpenCode ingest endpoint

Goal:

Let the plugin post its stable envelope into the existing loopback daemon.

Add:

```text
POST /hook/opencode
```

or the equivalent route matching the current server style.

Use the same:

```text
JDSL_INGEST_URL
JDSL_CAPTURE_ID
JDSL_HOOK_TIMEOUT
```

conventions used by Claude/Gemini where possible.

Do not create a second daemon.

### Behavior

The endpoint should:

1. validate the jdsl OpenCode envelope,
2. call the OpenCode adapter,
3. append canonical events,
4. return quickly.

The endpoint should not perform compiler-model work.

### Failure policy

Capture is observational.

Plugin failure should fail open.

The local daemon should log malformed envelopes clearly.

### Tests

Extend `test/test_server_cli.py` with:

```text
/hook/opencode
```

fixture ingestion.

---

## 10. PR 6: add `plugins/jdsl-opencode-plugin/`

Goal:

Ship a thin TypeScript plugin that forwards structured OpenCode events into the jdsl daemon.

Suggested layout:

```text
plugins/
└── jdsl-opencode-plugin/
    ├── README.md
    ├── jdsl.ts
    └── fixtures/
```

Keep the plugin thin.

It should not contain compiler logic.

### Required hooks

Start with stable hooks available in the installed OpenCode release:

```text
session lifecycle events
tool.execute.before
tool.execute.after
```

If the current stable API exposes more structured context safely, add it only after tests.

Do not make the initial plugin depend on beta v2 APIs.

### Plugin behavior

Pseudo-code only:

```ts
import type { Plugin } from "@opencode-ai/plugin"

export const JdslHarness: Plugin = async (ctx) => {
  return {
    event: async ({ event }) => {
      // forward selected session events
    },

    "tool.execute.before": async (input, output) => {
      // construct jdsl envelope
      // POST to localhost
      // fail open
    },

    "tool.execute.after": async (input, output) => {
      // same
    },
  }
}
```

The coding agent must inspect the installed OpenCode types before writing exact field access.

### Fail-open transport

Use a short timeout.

Default:

```text
JDSL_HOOK_TIMEOUT=0.5
```

If the daemon is down:

- do not break OpenCode,
- optionally emit one throttled local warning,
- continue tool execution.

### Redaction

The plugin should not invent its own separate redaction policy.

Forward structured payloads to the local harness.

Apply durable-persistence redaction in the shared harness layer.

Never log credentials to console for debugging.

### Installation docs

Document project-local installation first.

Conceptually:

```text
<project>/.opencode/plugins/jdsl.ts
```

Then document optional global installation:

```text
~/.config/opencode/plugins/
```

Prefer a symlink during development so changes in the repo are picked up without copying.

### Smoke test

Manual development flow:

```bash
export JDSL_HARNESS_HOME=/tmp/jdsl-opencode
export JDSL_CAPTURE_ID=cap_opencode
export JDSL_INGEST_URL=http://127.0.0.1:8848

uv run jdsl harness serve

opencode
```

Inside OpenCode, perform a task that makes several tool calls.

Then:

```bash
uv run jdsl capture list
uv run jdsl capture inspect cap_opencode
```

Acceptance requires:

- episode exists,
- tool calls have args/results,
- before/after events correlate,
- daemon failure does not break OpenCode.

---

## 11. Optional later OpenCode high-fidelity mode

Do not block the first plugin on this.

OpenCode's newer plugin work exposes richer model/context hooks.

A later adapter may capture:

- tools visible before selection,
- model-visible context size,
- compaction events,
- selected model metadata.

That would raise trace fidelity and help compare Skills against compiled packages.

Keep this behind a clearly documented compatibility mode until the API is stable.

Do not silently depend on beta APIs.

---

# Part III: finish Tier-A MCP proxying

## 12. PR 7: implement live transparent MCP proxy serving

Goal:

Turn the existing recording `MCPProxy` into a usable Tier-A gateway.

Current architecture already wants:

```text
host
-> jdsl MCP proxy
-> upstream MCP server
```

The missing work is transport wiring.

### Requirements

The proxy should:

1. connect to one configured upstream MCP server,
2. call upstream tool discovery,
3. expose the same tool schemas to the host,
4. namespace logical IDs predictably,
5. forward calls,
6. preserve results and errors,
7. record tool calls in canonical jdsl events,
8. record exposed tool-set metadata,
9. preserve cancellation/timeout semantics where supported,
10. shut down cleanly.

### Do not over-generalize transport in the first PR

Support the transport already used by the current harness dependency and tests.

Add another transport only in a separate PR.

### Configuration

Use a small explicit config.

Example conceptual shape:

```toml
[name]
logical_prefix = "retail"
transport = "stdio"
command = ["uv", "run", "..."]
```

or:

```text
upstream URL
```

depending on supported MCP transport.

### Schema preservation tests

Test:

- tool names,
- input JSON Schema,
- output shape,
- errors,
- annotations where available.

The host should not lose tool metadata because jdsl sits in the middle.

### Capture tests

One fake MCP server should be enough for offline CI.

Assert:

```text
list tools
call tool
canonical start event
canonical result event
exact args/result
```

### Docs honesty

Until the live proxy is implemented, docs should describe `MCPProxy` as a recording abstraction rather than implying all live proxy transport is production-ready.

---

# Part IV: make residual signatures fully executable

## 13. PR 8: define the runtime contract for a compiled signature

Goal:

Make every field in a compiled residual signature either operational or explicitly unsupported.

This is the most important package-runtime PR.

### Current conceptual signature

A compiled signature may contain:

```text
id
kind
inputs
output
instruction
examples
tools
context_policy
validator
```

Write a single contract document:

```text
docs/signatures.md
```

For each field specify:

- package representation,
- runtime behavior,
- validation,
- failure behavior.

### Do not add fields during this PR

First make the existing schema truthful.

---

## 14. PR 9: resolve signature inputs from their declared source paths

Goal:

A residual leaf should consume exactly the blackboard values named by the package.

Do not reduce a richer source path to a last field name if doing so loses semantics.

Example:

```text
input alias: orders
source: blackboard.customer.orders
```

Runtime should resolve the declared source.

Expose the alias to the model.

This keeps package internals separate from model-facing field names.

### Example

Package:

```json
{
  "inputs": {
    "orders": {
      "source": "orders",
      "schema": {"type": "array"}
    }
  }
}
```

or later:

```json
{
  "inputs": {
    "target_candidates": {
      "source": "customer.orders",
      "schema": {"type": "array"}
    }
  }
}
```

Model sees:

```text
target_candidates
```

not a full blackboard dump.

### Tests

- simple field.
- nested object.
- dynamic path if supported.
- missing ref.
- alias differs from source.
- RDB 0 unchanged.

---

## 15. PR 10: honor examples and context policy

Goal:

Allow a package to carry a few verified local demonstrations without turning into another giant Skill.

### Example policy

Signature:

```text
resolve_target_order
```

might include three verified examples.

Runtime should render only those examples for that leaf.

### Define a small context policy

Do not invent a huge prompt-management DSL.

Start with:

```text
max_examples
include_fields
max_instruction_chars or tokenizer-aware limit where available
```

If `context_policy` currently has different fields, implement the existing shape before extending it.

### Important rule

Examples should come from verified successful decisions.

Do not copy full trajectories into every leaf.

### Test

Use a spy model.

Assert the model request contains:

- local instruction,
- required fields,
- allowed examples.

Assert it excludes:

- unrelated blackboard fields,
- unrelated tools,
- other leaf examples.

This test directly proves the package reduces active policy context.

---

## 16. PR 11: enforce residual output validation before effectful actions

Goal:

A bad small-model output must fail before it becomes an unsafe or nonsensical tool argument.

### Example failure

Model returns:

```text
selected_index = 99
```

Orders contain only three entries.

Current dynamic ref resolution should not be allowed to reach an effectful call with an invalid target.

### Compiler/runtime behavior

After a residual index decision, insert or enforce:

```text
exists(orders[$selected_index])
```

before any action derived from that index.

Likewise:

- enum output must be one of allowed values,
- integer min/max should be enforced when known,
- boolean should parse predictably,
- invalid JSON/typed output should fail locally.

### First validator scope

Keep the validator small.

Support the subset needed by current package schemas:

```text
type
enum
minimum
maximum
```

Add more only with tests.

### Failure policy

For MVP:

```text
invalid residual output
-> leaf failure
-> tree selector/recovery if one exists
```

Do not silently coerce arbitrary invalid output.

Later, a bounded retry decorator may be added.

### Tests

- valid index.
- negative index.
- out-of-range index.
- invalid enum.
- residual failure does not call downstream destructive tool.

---

# Part V: capture real residual evidence

## 17. PR 12: normalize actual residual decision values

Goal:

Move from "a model decision occurred here" to "this exact local decision saw these values and produced this parsed output."

After PR 2, `Predict` trace has request/response events.

Extend normalized `ModelDecision` to hold:

```text
node_id
kind
input sources
observed input values or evidence refs
output name
observed parsed output
outcome
```

Respect redaction.

### Why

This enables:

- verified per-signature examples,
- per-leaf unit datasets,
- model error analysis,
- comparison across teachers,
- residual decomposition later.

### Consolidation

Group residual decisions by stable `node_id` or normalized signature identity.

Do not mix unrelated decisions because they happen to have the same field names.

---

## 18. PR 13: attach verified residual examples to signatures

Goal:

Turn successful teacher decisions into tiny leaf-local examples.

Selection algorithm should be deterministic initially.

Example:

1. gather successful examples for a residual signature,
2. deduplicate identical normalized examples,
3. choose a bounded diverse set,
4. store source evidence digests,
5. attach to `Signature.examples`.

Do not require embeddings for MVP.

Simple diversity may use:

- output-class coverage,
- input length buckets,
- deterministic hashing.

### Package provenance

Each example should retain:

```text
source episode digest
source decision node
verification status
```

### Runtime

PR 10 already makes examples operational.

This PR populates them.

---

# Part VI: add a supported small-model binding path

## 19. The Hugging Face integration should not pollute core

A Gemma experiment needs:

- `transformers`,
- `torch`,
- possibly `accelerate`.

These should not become required dependencies of the runtime core.

Current development constraint:

```text
do not run Gemma locally on the workstation
run Gemma in Colab or another GPU host
```

The repository should carry a notebook for the manual GPU path:

```text
docs/gemma_colab_experiment.ipynb
```

The notebook should:

- install this branch in Colab,
- install Hugging Face inference dependencies,
- authenticate to Hugging Face when needed,
- load the Gemma model from the Hub,
- import the jdsl package/runtime and example tools,
- run the existing deterministic package as a sanity check,
- run a residual `predict` playground where Gemma emits only `selected_index`,
- let jdsl resolve the exact downstream order ID deterministically.

Choose one of these paths.

### Recommended immediate path: model adapter file

Add CLI support for:

```text
--model-file local_model.py
```

The file exposes:

```python
MODEL = ...
```

where `MODEL` implements the existing `LanguageModel`-shaped interface.

Benefits:

- zero new core provider routing,
- works with any local runtime,
- easy notebooks,
- no ambiguity between hosted and local IDs,
- no forced torch dependency.

Then add an optional first-party helper in `jdsl_harness`.

### Recommended convenience helper

```text
jdsl_harness/models/huggingface.py
```

with:

```python
HuggingFaceGenerateModel
```

Implement only `generate()` first.

If a package contains residual `react` leaves, fail with a clear message unless the adapter supports `converse()` and tool calling.

Do not pretend text generation equals function calling.

---

## 20. PR 14: add `--model-file`

Goal:

Let `jdsl package run` bind a real model object without adding a cloud-provider ID.

Concept:

```bash
uv run jdsl package run retail-semantic.jdslpkg \
  --tools examples/retail_tools.py \
  --model-file examples/gemma_model.py \
  --input request="Cancel the shoes" \
  --input email=ada@example.com
```

Loader logic:

```text
import model file
require MODEL
pass MODEL to runtime
```

The same mechanism works for:

- Hugging Face,
- llama.cpp wrappers,
- MLX,
- vLLM client objects,
- custom local models.

### Safety

A model file is trusted local code supplied by the user.

It is not inside `.jdslpkg`.

Keep the package no-code rule intact.

### Test

Use a temporary model file exposing `FakeModel`.

No heavy dependencies in CI.

---

## 21. PR 15: add optional Hugging Face helper

Goal:

Make Gemma experimentation easy without changing the core runtime.

This PR should be notebook-first for Gemma. The acceptance path is a manual
Colab/GPU-host run, not a local CPU or local workstation GPU run.

Suggested optional extra:

```toml
local-models = [
    "transformers>=<tested-minimum>",
    "torch>=<tested-minimum>",
    "accelerate>=<tested-minimum>"
]
```

Do not guess minimum versions.

Pin the minimum only after the coding agent installs and tests the current official Gemma 4 path in Colab or another GPU host.

### Adapter contract

Implement:

```python
class HuggingFaceGenerateModel:
    model_id: str

    def generate(
        self,
        system: str,
        user: str,
        output_schema: dict | None = None,
    ) -> str:
        ...
```

Match the current jdsl model interface.

Record model identity.

Use deterministic generation settings in evaluation where supported:

```text
do_sample = false
```

### Gemma target

Start with:

```text
google/gemma-4-E2B-it
```

in the Colab notebook or another GPU host with enough memory for the tested inference path.

Do not assume any developer workstation can run it locally.

Provide a second tiny local test model option for smoke tests.

### Tool calling

Initial local Gemma demo should use only residual `predict`.

Do not require native tool calling.

The tree owns actions.

This is the cleanest proof of jdsl's value.

---

# Part VII: build the first real RDB greater than zero example

## 22. Promote the existing compiler test into a real example

The repository already proves the mechanics using `FakeModel`.

The next example should mirror that tested flow.

Suggested files:

```text
examples/harness/
├── retail_residual_capture.py
├── retail_residual_tools.py
├── gemma_model.py
└── README.md
```

Or keep the repository's current example layout if it prefers flat examples.

Do not introduce a new hierarchy solely for aesthetics.

### Task

Use one semantic choice.

Example dataset:

```text
customer has 3 orders
request says which order/item to act on
teacher chooses selected_index
tree performs exact downstream dataflow
```

Randomize:

- order IDs,
- order ordering,
- request wording,
- target position.

Do not let index 1 become a constant.

### Desired compiled package

Expected RDB:

```text
0 < RDB < 1
```

Ideal first package:

```text
meaningful decisions = 4
model-dependent decisions = 1
RDB = 0.25
```

### Desired runtime path

```text
lookup(email)
-> store customer

list_orders(customer.id)
-> store orders

predict(request, orders -> selected_index)
-> small model

guard selected_index valid

get_order(orders[$selected_index].id)
-> deterministic exact ref

perform read-only final action first
```

For the first public local-model demo, avoid irreversible writes.

Use:

```text
get_order
```

or a fake transactional environment.

Once the residual pipeline is proven, add cancellation with explicit guards in a separate example.

---

## 23. What the Gemma model should actually see

This should be documented with a spy trace.

Suppose input:

```text
request:
"Show me the order with the blue shoes."

orders:
[
  {"id":"#W991", "summary":"red shirt"},
  {"id":"#W2378156", "summary":"blue shoes"},
  {"id":"#W420", "summary":"black bag"}
]
```

The model should receive something close to:

```text
Instruction:
Choose the order the customer refers to.

request:
Show me the order with the blue shoes.

orders:
0: red shirt
1: blue shoes
2: black bag

Return:
selected_index as an integer
```

The model should not receive:

```text
how authentication works
all tool schemas
confirmation policy
the whole Behavior IR
exact downstream API procedure
recovery branches unrelated to this choice
```

Model output:

```text
1
```

Then jdsl resolves:

```text
orders[1].id
```

to:

```text
#W2378156
```

The small model never regenerates the ID.

This is the demo that should appear in docs.

---

## 24. Required tests for the real residual example

Keep CI offline.

Tests should use a spy/fake model.

Assert:

```text
package RDB > 0
package RDB < 1
exactly one model request occurs
model request belongs to expected signature
model sees only declared input fields
model does not see Behavior IR
model output changes downstream ref
downstream tool receives exact ID
invalid output blocks downstream action
same package accepts second fake model
RDB 0 package calls no model
```

The local Gemma run remains an opt-in integration/manual test.

---

# Part VIII: runtime telemetry and experiment metrics

## 25. PR 16: replace static "token" approximations with truthful naming

Current structural metrics are still useful.

Keep:

```text
RDB
deterministic coverage
exact dataflow refs/rate
visible tool branching
```

If a metric is calculated with:

```python
len(text.split())
```

name it:

```text
instruction_words
```

or:

```text
estimated_policy_tokens
```

Do not label it exact tokens.

Actual token measurements belong to runtime telemetry.

---

## 26. PR 17: add `InstrumentedModel`

Goal:

Measure actual model work for any runtime model.

A wrapper should record:

```text
model ID
node/signature ID
generate/converse call
start/end time
input size
output size
provider-reported usage if available
tokenizer-measured usage if local adapter supports it
errors
```

Do not make the wrapper provider-specific.

Concept:

```python
model = InstrumentedModel(gemma, recorder)
```

### Token priority

Use:

1. provider-reported token counts where authoritative,
2. local tokenizer counts where available,
3. character/word counts as explicitly labeled fallback.

Do not fake token precision.

### Tests

Wrap `FakeModel`.

Verify:

- call count,
- latency field,
- input/output sizes,
- node identity supplied through runtime context if available.

---

## 27. PR 18: add `EpisodeMetrics`

Derive run metrics from canonical traces.

Suggested object:

```text
EpisodeMetrics
```

Fields:

```text
success
reward
wall_time_ms

model_calls
model_time_ms
model_input_tokens
model_output_tokens

tool_calls
tool_time_ms
tool_failures

invalid_model_outputs
retries

nodes_visited
branches_visited
signatures_visited

policy_violations
exact_argument_failures

cold_start
```

Optional local-GPU extension:

```text
peak_cuda_memory_bytes
gpu_energy_joules
```

Keep GPU telemetry optional.

Do not pull NVML into core.

---

## 28. Add Model Work Fraction

RDB measures structure.

Model Work Fraction measures actual runtime burden.

Define separate fractions relative to a baseline.

### Model Call Fraction

```text
package model calls / baseline model calls
```

### Input Token Fraction

```text
package model input tokens / baseline model input tokens
```

### Output Token Fraction

```text
package model output tokens / baseline model output tokens
```

### Model Time Fraction

```text
package model inference time / baseline model inference time
```

Report savings as:

```text
1 - fraction
```

Example:

```text
RDB                         0.25
model call fraction         0.20
input token fraction        0.08
model time fraction         0.16
```

These metrics explain what compilation removed in actual execution.

---

# Part IX: compare `.jdslpkg` against Agent Skills

## 29. OpenCode gives us a strong baseline host

OpenCode supports Agent Skills.

Use that rather than inventing an intentionally weak "giant prompt" baseline.

The evaluation should distinguish:

```text
raw model
text Skill
full Agent Skill
compiled jdsl package
hybrid package + local textual examples
```

### Important fairness rule

The artifact formats should receive equivalent source knowledge.

Use the same:

- policy document,
- tool descriptions,
- teacher examples,
- task definition.

Do not give the package teacher trajectories while giving the Skill only a one-paragraph description.

If teacher trajectories are part of package construction, build a Skill baseline from the same evidence budget.

---

## 30. PR 19: add an evaluation runner

Suggested module:

```text
jdsl_harness/eval.py
```

Keep it small.

Avoid building a generic benchmarking framework.

Start with:

```python
run_arm(...)
compare_arms(...)
```

Experiment arm metadata:

```text
arm name
artifact type
artifact digest
model ID
task ID
seed
host
decoding config
timeout
```

### First arms

```text
raw
skill
package
hybrid
```

Fine-tuning arms come later.

### Paired evaluation

Run the same task/seed under every arm.

This reduces noise.

### Store raw run traces

Every evaluation run should be replayable.

Do not keep only aggregate CSV.

---

## 31. Separate executor quality from artifact routing

Agent Skills often require the host to decide whether a Skill should load.

A jdsl package may initially be selected explicitly.

Do not mix routing quality with execution quality.

### Experiment A: preselected artifact

The correct Skill/package is selected before task execution.

Measure:

```text
execution quality
runtime burden
policy compliance
```

### Experiment B: artifact routing

Give the system multiple Skills/packages.

Measure:

```text
selection precision
selection recall
downstream success
```

Do Experiment A first.

---

## 32. Metrics for Skill versus package

Measure at least:

```text
task pass rate
environment reward

model calls
input tokens
output tokens
model inference time

wall time
tool calls
tool errors

invalid tool calls
exact argument errors
retries

policy violations

active instructions loaded
tools visible per model decision

artifact size
artifact build cost
```

For jdsl also report:

```text
RDB
deterministic coverage
exact dataflow rate
node coverage
branch coverage
residual signature coverage
```

For Skills, convert important procedural instructions into testable constraints.

Example:

```text
constraint:
confirmation before write
```

Then mark each episode:

```text
not exercised
passed
failed
```

Otherwise a Skill can "pass" tasks without the benchmark ever exercising important instructions.

---

## 33. Required ablations

A final package versus Skill score does not tell us why a package works.

Add ablations.

### A: package without exact refs

Force model regeneration of opaque IDs.

Measures deterministic dataflow value.

### B: package without guard

Move confirmation/policy condition into local text.

Measures structural guard value.

### C: package with all tools exposed to residual leaf

Measures tool-space reduction.

### D: residual instructions only

Give the model the local signature text but remove tree control.

Measures control-flow value.

### E: Skill with deterministic helper scripts

This is the strongest fair Skill baseline.

Do not compare jdsl only to prose when Skills are allowed executable scripts.

### F: package without residual examples

Measures local example value.

---

# Part X: quantify avoided fine-tuning

## 34. Do not claim saved fine-tuning cost without a counterfactual

A `.jdslpkg` with zero weight changes has obvious training cost of zero for the student.

That alone does not quantify how much fine-tuning was "saved."

To measure displacement, train a baseline.

### Later training arms

Use the same base small model:

```text
raw frozen
Skill frozen
package frozen
end-to-end QLoRA
package + residual-only QLoRA
```

### Learning curve

Train QLoRA at budgets such as:

```text
25
50
100
250
500
1000 examples
```

Use actual budgets appropriate to the dataset.

Track:

```text
training examples
training tokens
GPU-hours
wall time
peak VRAM
training energy if measured
adapter size
held-out task score
```

### Fine-tuning displacement metric

Let:

```text
q_pkg = held-out score of frozen package arm
```

Find the smallest tuning budget whose confidence interval reaches `q_pkg`.

Report:

```text
examples to match package
training tokens to match package
GPU-hours to match package
wall time to match package
```

If no tested checkpoint matches:

```text
not matched within tested budget
```

This is defensible.

---

## 35. Residual-only fine-tuning is the more interesting later experiment

Once the package owns:

- sequencing,
- exact dataflow,
- guards,
- fixed actions,
- tool selection,

training data no longer needs to teach those behaviors.

Train only residual signatures.

Example dataset:

```text
request, orders -> selected_index
```

Compare:

```text
full-trajectory QLoRA
vs
residual-only QLoRA + same package
```

Measure samples and GPU-hours to a common held-out score.

This tests whether behavior compilation reduces the scope of post-training as well as inference burden.

Do not implement this before the inference-time evaluation is reliable.

---

# Part XI: documentation plan

## 36. Continue documentation with one concept per file

Recommended docs:

```text
docs/harness.md
    implementation map and current status

docs/harness_usage.md
    capture -> inspect -> compile -> run

docs/opencode.md
    install and use OpenCode capture plugin

docs/local_models.md
    bind local models to RDB>0 packages

docs/gemma_colab_experiment.ipynb
    manual Colab/GPU-host Gemma experiment for jdsl residual leaves

docs/evaluation.md
    raw/Skill/package experiments and metrics

docs/signatures.md
    exact residual-signature runtime contract
```

Avoid duplicating the same command across four docs.

Link between them.

---

## 37. Update `docs/harness.md` as code changes

Add a status table.

Example:

```text
feature                         status
canonical trace                 implemented
Claude hooks                    implemented
Gemini hooks                    implemented
OpenCode hooks                  implemented
recording MCP proxy             implemented
live MCP proxy transport        implemented/experimental
RDB>0 fake-model runtime        implemented
RDB>0 local HF runtime          experimental
runtime telemetry               implemented
Skill comparison runner         experimental
package signing                 not implemented
```

Never let design language imply a feature is shipped when it remains an extension point.

---

## 38. Create `docs/opencode.md`

Required sections:

```text
requirements
check installed OpenCode version
project-local plugin installation
global plugin installation
start jdsl daemon
environment variables
start capture
run OpenCode
inspect capture
compile package
capture fidelity
fail-open behavior
troubleshooting
uninstall
```

Show real commands tested on the developer machine.

Do not paste hypothetical commands without running them.

Include:

```bash
opencode --version
```

output in the development notes, not necessarily permanent docs.

---

## 39. Create `docs/local_models.md`

Required sections:

### RDB 0

Explain:

```text
no model is needed
passing a model changes nothing
```

### RDB greater than zero

Explain:

```text
tree executes
residual leaf invokes model
model receives local signature only
parsed output returns to blackboard
deterministic execution resumes
```

### Model object binding

Document `--model-file`.

### Gemma example

For current development, show the Colab notebook path first:

```text
docs/gemma_colab_experiment.ipynb
```

It should load Gemma from Hugging Face on a Colab GPU and bind it through the
same model-object interface used by `--model-file`.

Only show local workstation commands after they work on the target machine.

Future local/GPU-host command shape:

```bash
uv sync --extra local-models

uv run jdsl package run \
  retail-residual.jdslpkg \
  --tools examples/retail_tools.py \
  --model-file examples/gemma_model.py \
  --input email=ada@example.com \
  --input request="Show me the blue-shoes order"
```

Do not publish this as a local requirement until it has been tested on the target
machine.

### Model compatibility

Document package requirements:

```text
predict-only residuals
react/tool-calling residuals
structured output requirements
context limits
```

---

## 40. Create `docs/evaluation.md`

Document:

```text
experiment arms
paired task setup
fixed model settings
runtime metrics
RDB
Model Work Fraction
Skills baseline
ablations
fine-tuning displacement
reproducibility
```

Every published result should record:

```text
git commit
package digest
source capture digest
model ID/revision
OpenCode version if used
task dataset revision
seed
hardware
```

---

# Part XII: robustness backlog after the first experiment

## 41. Implement actual LLM compiler proposal roles

Only after runtime semantics and telemetry are solid.

Finish the compiler model so model-backed mode actually performs the roles documented for it.

Good uses:

```text
semantic grouping
candidate guard proposal
residual decomposition proposal
instruction wording
counterexample hypotheses
```

Keep deterministic verification authoritative.

Every model-produced proposal must still pass evidence checks.

---

## 42. Iterative residual decomposition

After a real Gemma run identifies a weak residual signature:

```text
request + policy + order -> allowed_action
```

ask the frontier compiler whether it can split the leaf.

Possible result:

```text
request -> requested_action          model
order -> state                       deterministic
requested_action + state -> key      deterministic
key -> allowed_action                deterministic
```

Then re-run Gemma.

Measure whether:

```text
RDB
input tokens
error rate
```

fall.

This is a later compiler optimization.

Do not build it before collecting real residual failures.

---

## 43. Package compatibility and version migrations

Before public package distribution, define:

```text
IR format version
package format version
signature format version
minimum runtime version
```

Add migration only when a real breaking change occurs.

Do not prematurely build a generalized migration engine.

Package loader error messages should clearly distinguish:

```text
unsupported package version
unsupported node
missing capability
invalid digest
invalid signature
```

---

## 44. Package signing

Signing remains later work.

Before a registry or package exchange, add optional signatures over the package digest.

The no-arbitrary-code rule remains the primary safety boundary.

Signing authenticates origin.

It does not make a bad policy safe.

---

# Part XIII: coding-agent execution order

## 45. Recommended order

Coding agents should work through this sequence.

### Phase 0: baseline

```text
read branch
run tests
run ruff
record commit
```

### Phase 1: robustness

```text
PR 1  full lint/CI coverage
PR 2  Predict model tracing
PR 3  host tool correlation
```

### Phase 2: OpenCode

```text
PR 4  Python OpenCode adapter
PR 5  ingest endpoint
PR 6  TypeScript OpenCode plugin + docs
```

### Phase 3: capture completeness

```text
PR 7  live MCP proxy transport
```

### Phase 4: residual runtime

```text
PR 8   signature contract doc
PR 9   source-path resolution
PR 10  examples/context policy
PR 11  output validation
PR 12  normalize real residual evidence
PR 13  verified residual examples
```

### Phase 5: small local model

```text
PR 14  --model-file
PR 15  optional HF/Gemma adapter + Colab notebook
RDB>0 real example
```

The RDB>0 example may be included in PR 15 or a separate one if repository review prefers one idea per PR.

### Phase 6: measurement

```text
PR 16  truthful static metric names
PR 17  InstrumentedModel
PR 18  EpisodeMetrics
PR 19  evaluation runner
```

### Phase 7: experiments

```text
raw vs Skill vs package
second small-model family
ablations
```

### Phase 8: later research

```text
LLM compiler proposal roles
iterative residual decomposition
fine-tuning displacement
signing/registry
```

---

# Part XIV: definition of done for the next milestone

## 46. Milestone: "portable residual behavior"

The next milestone is done when all of these pass.

### Harness

```text
Claude capture works
Gemini capture works
OpenCode capture works
MCP proxy capture works
tool calls correlate under concurrency
Predict and React model events are traceable
```

### Compiler

```text
RDB 0 package still works
RDB > 0 package compiles
residual inputs and outputs are evidenced
dynamic refs work after residual output
invalid residual output blocks downstream action
```

### Package

```text
no arbitrary code
all digests verify
all capabilities bind before run
signature semantics are honored
```

### Small model

```text
real Gemma runs one predict residual in Colab or another GPU host
model sees only leaf-local context
one model output drives later deterministic state
same package runs with another model
```

### OpenCode

```text
plugin installs locally
capture daemon may be unavailable without breaking OpenCode
tool events appear in capture
compiled package builds from captured evidence
```

### Measurement

```text
actual model calls measured
actual input/output token counts measured where tokenizer/provider supports them
model latency measured
tool latency measured
RDB and deterministic coverage reported
```

### Evaluation

```text
raw arm exists
OpenCode Agent Skill baseline exists
jdsl package arm exists
same small model and tasks used
paired results reported
```

---

# Part XV: first end-to-end experiment to run

## 47. Experiment A: OpenCode capture -> RDB>0 package -> Gemma

Use a deliberately small task family.

Do not start with all retail tasks.

### Step 1

Run a strong model in OpenCode with the jdsl plugin enabled.

Capture several semantically varied episodes.

Ensure a target-selection decision changes across examples.

### Step 2

Inspect:

```bash
uv run jdsl capture inspect <capture>
```

Confirm:

```text
exact dataflow exists
semantic decision exists
capture fidelity supports the decision
```

### Step 3

Compile:

```bash
uv run jdsl compile <capture> \
  --name retail-order-selection \
  --out retail-order-selection.jdslpkg
```

Require:

```text
verification passed
0 < RDB < 1
```

### Step 4

Inspect package:

```bash
uv run jdsl package inspect retail-order-selection.jdslpkg
```

Confirm:

```text
one residual signature
few/no tools visible to it
dynamic ref follows selected_index
```

### Step 5

Run with a fake spy model.

This is the deterministic sanity test.

### Step 6

Run with Gemma in Colab or another GPU host.

Record:

```text
model calls
input tokens
output tokens
model latency
tool latency
success
```

### Step 7

Run the same package with a second small model.

Do not recompile.

### Step 8

Run the equivalent OpenCode Agent Skill baseline with the same small model and same task source.

Measure the same metrics.

### Step 9

Run ablations:

```text
remove deterministic ID ref
expose all tools
replace guard with text instruction
```

### Step 10

Publish the experiment with:

```text
commit SHA
package digest
capture digest
OpenCode version
model revision
task fixtures
hardware
```

That is enough to make the first serious jdsl behavior-transfer claim.

---

# Part XVI: first end-to-end experiment to avoid

## 48. Do not start with a large benchmark claim

Avoid jumping directly to:

```text
all tau retail
many hosts
many models
fine-tuning
```

before the residual execution path is observable.

A large benchmark with poor telemetry will tell you only that a score changed.

The first experiment should answer:

> Did the compiled package move procedural work out of the small model while preserving the one semantic decision the model still needed to make?

If yes, scale.

---

# Part XVII: coding-agent checklist

## 49. Before every PR

```text
[ ] checkout harness
[ ] read touched modules
[ ] read nearby tests
[ ] run baseline pytest
[ ] run ruff including jdsl_harness
[ ] keep one main idea
[ ] keep core dependency-light
[ ] no network in unit tests
[ ] no arbitrary package code
```

## 50. Before marking every PR done

```text
[ ] happy path tested
[ ] failure path tested
[ ] docs updated
[ ] public behavior documented
[ ] no stale design claim
[ ] pytest passes
[ ] ruff passes
[ ] package compatibility checked
```

## 51. Before any benchmark result is reported

```text
[ ] source commit recorded
[ ] package digest recorded
[ ] capture digest recorded
[ ] model revision recorded
[ ] hardware recorded
[ ] task revision recorded
[ ] seeds recorded
[ ] raw traces retained
[ ] model work measured
[ ] tool work measured
[ ] paired baseline run
[ ] confidence interval reported
```

---

# Part XVIII: key implementation principles

## 52. The package runs the model, not the other way around

Do not inject the full `.jdslpkg` into Gemma.

The interpreter loads the package.

The interpreter reaches:

```text
predict(request, orders -> selected_index)
```

Only then does Gemma run.

The result returns to the blackboard.

The interpreter resumes deterministic execution.

That is the architecture.

---

## 53. RDB 0 and RDB greater than zero are different products

RDB 0:

```text
package = complete executable policy
model = unnecessary
```

RDB greater than zero:

```text
package = executable policy + typed semantic holes
model = local hole solver
```

Document both clearly.

Do not use an RDB 0 demo as evidence of small-model behavior transfer.

Use the real RDB>0 demo.

---

## 54. OpenCode should be an evidence source before it becomes an execution dependency

The first OpenCode integration should capture behavior.

Do not require OpenCode to run a package.

A `.jdslpkg` should remain portable.

OpenCode is valuable because it gives:

```text
frontier capture
Agent Skills comparison
host-level tool telemetry
```

The behavior artifact should remain independent of it.

---

## 55. Measurement comes before fine-tuning

Before asking whether jdsl saves fine-tuning:

measure how much model work the package removes.

Once runtime measurements are reliable, compare against QLoRA.

Otherwise "saved training" becomes a claim without a counterfactual.

---

## 56. Do not turn compiled behavior back into prose

The compiler's job is to remove procedural interpretation from the model.

If a candidate behavior is:

```text
always preserve returned order_id exactly
```

compile:

```text
ref(order.id)
```

Do not generate:

```text
"Remember to preserve the exact order ID."
```

If a candidate behavior is:

```text
do not write before confirmation
```

compile:

```text
guard(confirmation)
```

Do not generate:

```text
"Always remember to ask for confirmation."
```

Text is the residual representation.

Structure is the preferred representation when evidence safely supports it.

---

# Part XIX: source references

Repository and branch:

https://github.com/Cantor-Industries/jdsl-py/tree/harness

Current repository contribution style:

https://github.com/Cantor-Industries/jdsl-py/blob/harness/CONTRIBUTING.md

Current harness usage:

https://github.com/Cantor-Industries/jdsl-py/blob/harness/docs/harness_usage.md

Current compiler tests:

https://github.com/Cantor-Industries/jdsl-py/blob/harness/test/test_compiler.py

Current runtime:

https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/tree.py

Current IR lowering:

https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/ir/lower.py

Current package loader:

https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/package/load.py

Current compiler model:

https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/compiler/model.py

Current metrics:

https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/metrics.py

Current MCP proxy:

https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/mcp_proxy.py

OpenCode plugin documentation:

https://opencode.ai/docs/plugins/

OpenCode Agent Skills documentation:

https://opencode.ai/docs/skills/

Gemma 4 E2B model card:

https://huggingface.co/google/gemma-4-E2B-it

---

## 57. Immediate instruction to the coding agents

Start with the branch as it exists.

Do not rewrite the harness.

The first implementation batch should be:

```text
1. full harness quality gate
2. Predict trace parity
3. host tool-call correlation
4. OpenCode adapter
5. OpenCode ingest endpoint
6. OpenCode TypeScript plugin
7. docs/opencode.md
```

Then:

```text
8. live MCP proxy
9. complete residual signature runtime semantics
10. real RDB>0 package example
11. --model-file
12. Hugging Face/Gemma adapter, Colab notebook, and docs
13. runtime telemetry
14. raw vs Skill vs package evaluator
```

The next research checkpoint is not another architecture document.

It is one reproducible run showing:

```text
OpenCode frontier trace
-> compiled verified .jdslpkg
-> RDB > 0
-> frozen Gemma solves the residual leaf
-> deterministic jdsl structure handles the rest
-> same package runs with another small model
-> runtime work is measured
-> Agent Skill baseline is measured on the same task
```

Once that is working, the project has the evidence needed to decide which compiler improvements matter next.
