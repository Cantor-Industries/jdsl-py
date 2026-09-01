# jdsl Behavior Compiler Harness

## Engineering design for extracting frontier-model behavior into portable policies for smaller frozen language models

Research snapshot: 2026-08-20

Status: design proposal

Repository considered: `Cantor-Industries/jdsl-py`

---

## 1. Executive summary

The strongest version of the jdsl idea is not "give a small model a better prompt."

The stronger idea is:

> Let a frontier model perform difficult tasks. Record the observable structure of successful behavior. Convert reusable parts of that behavior into executable jdsl policy. Leave only the irreducibly semantic decisions as small, typed model signatures. Run the resulting package with a smaller frozen model.

No model weights change.

The transfer happens through an external artifact.

Current Agent Skills already transfer procedural knowledge at inference time. Anthropic Skills use progressive disclosure: metadata stays present, the main `SKILL.md` loads when triggered, and deeper files or scripts load as needed.[^skills-anthropic] This reduces context pressure, but a model still has to read procedural text, decide which instruction applies, remember state, select tools, preserve exact values, recover from failures, and respect ordering rules.

Research from SkillsBench makes the limitation concrete. Curated Skills improved average pass rate, but the effect varied sharply. Some tasks became worse. Focused Skills with only a few modules outperformed broad documentation, and self-generated Skills did not help on average.[^skillsbench] This suggests that procedural context helps, but more procedural text is not a reliable path.

Trace2Skill and SkillX move another step forward. They extract reusable skills from trajectories and report transfer across models without weight updates.[^trace2skill][^skillx] Their output still centers on declarative skills or retrieved skill knowledge.

jdsl should target a different output:

> executable behavior, not only executable advice.

A frontier model should not merely write a better `SKILL.md`. The compiler should decide which learned behavior belongs in:

- deterministic control flow,
- exact dataflow,
- guards,
- fixed actions,
- tool visibility,
- bounded recovery,
- postcondition checks,
- or a residual language-model signature.

The small model receives only the residual decision active at the current tree node.

The harness therefore has four jobs:

1. Capture high-fidelity observable trajectories.
2. Convert raw host-specific traces into one canonical event model.
3. Mine and verify reusable behavior from many trajectories.
4. Compile verified behavior into a safe, portable jdsl package.

The recommended system has three products inside one project:

- `jdsl` runtime: the existing tree interpreter.
- `jdsl-harness`: capture daemon, MCP control plane, tool proxy, host adapters, trace store.
- `jdsl-compiler`: behavior mining, verification, lowering, package export.

The recommended distribution artifact is an unpacked behavior directory during development and a deterministic `.jdsl` ZIP for transport.

The package should contain no arbitrary generated Python by default.

A package should contain a restricted behavior IR, typed residual signatures, tool contracts, tests, provenance, and verification metadata.

The central compiler rule should be:

> If a behavior is safely representable without asking the small model, remove that behavior from the small model.

---

## 2. The problem jdsl should solve

### 2.1 Current Skills still spend model cognition on procedure

Modern Skills already avoid loading every reference file at startup. That is useful.

The remaining problem is active procedural complexity.

Suppose a customer-support Skill contains:

- authentication requirements,
- order lookup procedure,
- return policy,
- cancellation policy,
- confirmation requirements,
- exceptions,
- tool schemas,
- retries,
- failure handling,
- formatting rules,
- examples.

Even with progressive disclosure, a small model still has to interpret some procedural text during execution.

The model must infer:

- where the current task sits in the workflow,
- which rule applies now,
- which tool is valid now,
- which value from an earlier result must become a later argument,
- whether a user has confirmed the exact pending operation,
- whether a failed call deserves retry, fallback, or stop.

For a strong model, this is often manageable.

For a weak model, nominal context length is only one issue. A small model might advertise a large token window and still use large procedural contexts poorly. The better target is therefore not "fit the Skill inside the context window." The target is "reduce the amount of policy the model must actively interpret per decision."

### 2.2 Text compression is not enough

Prompt compression asks:

> How do we express the same policy with fewer tokens?

Behavior compilation asks:

> Which parts of this policy should stop being language-model decisions?

That distinction should define jdsl.

Example:

A textual skill says:

1. Authenticate the customer before viewing account data.
2. Retrieve the order.
3. If several orders match, ask which one.
4. Check cancellation eligibility.
5. Ask for explicit confirmation.
6. Execute cancellation only after confirmation.
7. Verify the new order state.

A compiled policy might execute:

```text
authenticate
  -> store customer_id
  -> list_orders(customer_id)
  -> resolve target order        [small model]
  -> get_order(exact order_id)
  -> guard cancellable
  -> prepare operation
  -> request confirmation
  -> guard confirmation matches pending operation
  -> cancel_order(exact order_id)
  -> verify postcondition
  -> explain result              [small model]
```

Only two steps in this example require language generation or interpretation.

### 2.3 The most important metric is residual model burden

Context tokens matter.

Tool count matters.

The number of decisions delegated to the model matters more.

Define:

`Residual Decision Burden (RDB)`

```text
RDB = model-dependent decision points / total meaningful decision points
```

A raw agent might have:

```text
25 meaningful decisions
25 model-dependent decisions
RDB = 1.00
```

A compiled package might have:

```text
25 meaningful decisions
5 model-dependent decisions
RDB = 0.20
```

The small model did not become smarter.

The runtime gave the small model less responsibility.

---

## 3. Prior work and where jdsl should differ

### 3.1 Agent Skills

Anthropic's Agent Skills package instructions, scripts, and resources in directories. Progressive disclosure loads metadata first, then the main instructions, then deeper resources as needed.[^skills-anthropic]

This is already better than one giant system prompt.

The jdsl opportunity starts where progressive disclosure ends.

A Skill says:

> Here is the procedure. Apply the relevant parts.

A compiled jdsl package says:

> The procedure is already running. Solve this one local decision.

### 3.2 SkillsBench

SkillsBench evaluated Agent Skills across many tasks and model-agent configurations. The paper reports an average gain from curated Skills, wide task-level variation, negative deltas on some tasks, no average gain from self-generated Skills, and better results from focused Skills than comprehensive documentation.[^skillsbench]

This gives jdsl three design requirements:

1. Do not assume more procedural text helps.
2. Verify every compiled behavior against held-out evidence.
3. Minimize the active instruction set given to each model leaf.

### 3.3 Trace2Skill

Trace2Skill extracts trajectory-local lessons in parallel and consolidates those lessons into a conflict-free skill directory.[^trace2skill]

This is close to the front half of the proposed jdsl compiler.

jdsl should reuse the high-level lesson:

- analyze many traces,
- extract local evidence,
- consolidate across traces,
- search for conflicts.

jdsl should change the output target.

Instead of asking only:

> What guidance belongs in the Skill?

jdsl asks:

> Does this guidance belong in text at all?

### 3.4 SkillX

SkillX builds hierarchical skill knowledge from a strong backbone and reports transfer to weaker agents on agent benchmarks.[^skillx]

SkillX is direct evidence that strong-to-weak behavior transfer through external artifacts is plausible.

jdsl should push one step further:

```text
retrieved procedural knowledge
        ->
compiled executable policy
        +
small residual signatures
```

### 3.5 Schema Harness

Schema Harness requires an agent to externalize an environment model into executable code, backtest that model against prior transitions, plan inside the validated model, execute through a commit path, and discard a plan after prediction mismatch.[^schema]

The public Schema traces include append-only events, snapshots, notes, and generated world models.[^schema-traces]

jdsl should borrow four principles:

1. Evidence should remain append-only.
2. Model-generated structure should pass replay before trust.
3. Consequential actions should go through a controlled execution path.
4. A mismatch between expected and observed state should invalidate dependent plans.

Schema focuses on executable models of an environment.

jdsl should focus on reusable executable policy across tasks and models.

The two ideas fit together later through action preconditions and postconditions.

---

## 4. The core abstraction

### 4.1 Behavior is not hidden reasoning

The harness does not need private chain-of-thought.

The harness needs observable evidence:

```text
state
-> available actions
-> chosen action
-> arguments
-> result
-> new state
-> later outcome
```

A useful behavior is a reusable relation across those observables.

Examples:

```text
customer_id returned by authentication
-> customer_id argument used by list_orders
```

```text
write operation requested
+ no matching confirmation
-> do not execute write
```

```text
lookup returns not_found
-> try account-level enumeration
```

```text
several candidate orders
-> ask or predict which order the user means
```

### 4.2 Six initial behavior atom types

The first compiler only needs six categories.

#### CONTROL

Ordering or branching.

Examples:

```text
authenticate before account operations
retrieve before mutate
verify after write
```

Lowering targets:

```text
seq
sel
repeat
optional
oneshot
timeout
```

#### DATAFLOW

Exact value movement.

Examples:

```text
lookup.customer_id -> list_orders.customer_id
orders[chosen].id -> get_order.order_id
```

Lowering targets:

```text
store
ref
blackboard paths
```

#### GUARD

State predicates controlling execution.

Examples:

```text
confirmed == true
order.status in cancellable_states
target_order exists
```

Lowering target:

```text
guard/check + selector structure
```

#### ACTION

A known operation in a known state.

Examples:

```text
after authentication, retrieve orders
after confirmed cancellation, call cancel_order
```

Lowering target:

```text
act
```

#### RECOVERY

A known failure-to-recovery relation.

Examples:

```text
lookup_by_id.not_found -> enumerate_account_orders
transient_error -> bounded retry
ambiguous_target -> request clarification
```

Lowering targets:

```text
sel
repeat
optional
explicit recovery subtree
```

#### SEMANTIC

A decision that still requires model judgment.

Examples:

```text
transcript + candidate orders -> selected order
user message -> intent enum
tool result + user request -> concise response
```

Lowering targets:

```text
predict
react
```

The compiler should treat `SEMANTIC` as the residue, not the default.

---

## 5. What jdsl already has

The current repository already has the right execution primitives.[^jdsl]

The README describes:

- `root`
- `seq`
- `sel`
- `repeat`
- `invert`
- `optional`
- `timeout`
- `oneshot`
- `act`
- `ref`
- `store`
- `check`
- `predict`
- `react`

The runtime already separates deterministic control from model leaves.

That is the main reason this project is viable.

### 5.1 Blackboard provenance already exists

`RunContext` carries a blackboard.

The current blackboard tracks writes and writer provenance.[^jdsl-context]

This is valuable because data lineage is central to compilation.

The compiler should extend this idea from runtime blackboard lineage to cross-host execution lineage.

### 5.2 `predict` already has local context semantics

The current `Predict` implementation reads named blackboard fields and makes a local model request.[^jdsl-tree]

That fits residual signatures.

The compiler should enrich the signature representation without replacing the simple user syntax.

### 5.3 `react` already scopes tools

The current `React` leaf receives an explicit list of tools.[^jdsl-tree]

That is critical for small models.

A compiled behavior should narrow tool visibility per leaf.

### 5.4 Current gaps

The main missing pieces are:

1. No general append-only execution trace.
2. `react` keeps its internal tool trajectory locally and ultimately writes the final result to the blackboard. The compiler needs those internal calls.
3. `check` is narrow for compiled state predicates.
4. Signatures are compact strings rather than first-class typed package objects.
5. No serializable behavior IR.
6. No behavior package loader.
7. No cross-host capture layer.
8. No compiler or verifier.
9. No stable node IDs intended for compiled artifacts.

These are additive changes.

The existing authoring API should remain valid.

---

## 6. Product architecture

Treat the system as two distributed artifacts and three software layers.

### 6.1 Artifact A: the jdsl harness plugin

This is what a user installs in a frontier-model host.

The plugin provides:

- capture controls,
- trace recording,
- behavior compilation,
- verification,
- package export.

The host-specific wrapper differs by platform.

The backend stays common.

### 6.2 Artifact B: the behavior package

This is what the user downloads after compilation.

Example:

```text
retail-cancellation.jdsl
```

This package runs later with a smaller model.

The behavior package is model-neutral where possible.

### 6.3 Software layers

```text
+------------------------------------------------------+
| Frontier host                                        |
| Claude Code / Gemini CLI / ChatGPT / custom agent    |
+----------------------------+-------------------------+
                             |
                             | control
                             v
+------------------------------------------------------+
| jdsl-harness                                         |
| MCP control plane                                    |
| capture coordinator                                  |
| host adapters                                        |
| MCP proxy / tool gateway                             |
| canonical event log                                  |
| state adapters                                       |
+----------------------------+-------------------------+
                             |
                             v
+------------------------------------------------------+
| jdsl-compiler                                        |
| normalize -> mine -> verify -> staticize -> lower    |
| residualize -> replay -> package                     |
+----------------------------+-------------------------+
                             |
                             v
+------------------------------------------------------+
| .jdsl                                             |
| behavior IR + signatures + contracts + tests         |
+----------------------------+-------------------------+
                             |
                             v
+------------------------------------------------------+
| jdsl runtime + frozen small model                    |
+------------------------------------------------------+
```

---

## 7. The most important architectural split: control plane vs telemetry plane

Do not send every trace event through an MCP tool call.

MCP should control the harness.

MCP should not be the only high-volume telemetry transport.

### 7.1 MCP control plane

Expose operations such as:

```text
jdsl.capture.start
jdsl.capture.finish
jdsl.capture.status
jdsl.capture.mark_outcome

jdsl.compile
jdsl.compile.status

jdsl.verify
jdsl.inspect
jdsl.export
```

MCP supports typed tool inputs and outputs through JSON Schema.[^mcp-tools]

For long compiler jobs, MCP task support exists in the current protocol family.[^mcp-tasks]

Do not depend on transport-level session state.

Return an explicit `capture_id`.

Require the caller to pass `capture_id` on later operations.

### 7.2 Telemetry data plane

Execution events should travel through one of:

- in-process trace sink,
- local Unix socket,
- loopback HTTP endpoint,
- local append-only spool,
- direct gateway instrumentation.

The telemetry path should be fast.

Host hooks often run synchronously inside the agent loop. Gemini CLI documents synchronous hook execution.[^gemini-hooks]

A slow remote request on every tool event would directly slow the agent.

Recommended local path:

```text
host hook
-> local jdsl ingest
-> append event
-> return immediately
```

A background daemon may batch persistence or remote upload after local append.

The hook itself should fail open for pure observation unless the user explicitly enables enforcement mode.

---

## 8. Capture architecture

No single capture technique works across every host.

Build three capture tiers.

## 8.1 Tier A: jdsl tool gateway

This is the preferred mode.

The model sees task tools through jdsl.

```text
frontier model
-> jdsl tool gateway
-> real task tool
```

The gateway records:

- tool identity,
- schema,
- arguments,
- start time,
- result,
- error,
- duration,
- state before,
- state after,
- action mutability.

### 8.1.1 MCP proxy mode

This should be a major feature.

Many modern tools already arrive through MCP.

jdsl should act as a transparent MCP proxy:

```text
frontier host
-> jdsl MCP proxy
-> upstream MCP server
```

The proxy:

1. discovers upstream tools,
2. preserves input and output schemas,
3. exposes namespaced tools to the host,
4. forwards calls,
5. records full calls and results,
6. records upstream server identity,
7. optionally calls state observers around mutations.

This avoids writing wrappers for every MCP tool.

Example CLI concept:

```bash
jdsl harness serve
jdsl proxy add github --transport stdio --command "..."
jdsl proxy add retail --url http://localhost:9001/mcp
```

The exact CLI syntax is not important yet.

The architectural point is important.

For MCP-native task environments, jdsl gains complete tool-call visibility through one generic proxy.

## 8.2 Tier B: host-hook capture

An MCP server does not automatically see a host's native tools.

Host adapters fill this gap.

### Claude Code

Claude Code exposes lifecycle hooks including:

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `PostToolBatch`
- `SubagentStart`
- `SubagentStop`
- `SessionEnd`

Tool hook inputs contain tool names, inputs, and post-tool results.[^claude-hooks]

A jdsl Claude plugin should install hook definitions that forward normalized events to the local harness.

The hook adapter should never depend on scraping terminal text.

Use the structured JSON hook payload.

### Gemini CLI

Gemini CLI exposes a broad hook surface including:

- `SessionStart`
- `SessionEnd`
- `BeforeAgent`
- `AfterAgent`
- `BeforeModel`
- `AfterModel`
- `BeforeToolSelection`
- `BeforeTool`
- `AfterTool`
- `PreCompress`

Gemini also supports filtering the tool set before tool selection.[^gemini-hooks][^gemini-hooks-ref]

This host offers an interesting future enforcement path.

A compiled jdsl policy might drive tool filtering directly through `BeforeToolSelection`.

For the first release, use the hooks for capture only.

### Hosts without global tool hooks

For ChatGPT-style custom MCP integrations or other clients where the jdsl plugin lacks visibility into native host tools, use:

- jdsl-owned gateway tools,
- imported traces,
- or a custom agent SDK integration.

Do not claim full capture when the plugin only sees jdsl MCP calls.

Record capture fidelity in every trace.

## 8.3 Tier C: imported traces

Benchmarks and existing agent frameworks already emit logs.

The harness should support import adapters:

```text
Schema events.jsonl
tau-style task trajectories
OpenAI Responses traces
custom JSONL
Claude session logs
Gemini session logs
```

Every importer maps into the same canonical jdsl event schema.

---

## 9. Capture fidelity levels

A compiler should know what evidence exists.

Suggested levels:

### F0: outcome only

Known:

- task input,
- final answer,
- final reward.

Poor for behavior extraction.

### F1: transcript

Adds:

- user messages,
- assistant messages.

Useful for semantic analysis.

### F2: tool trace

Adds:

- tool names,
- arguments,
- results,
- errors,
- order.

This should be the minimum practical level for behavior compilation.

### F3: state transition trace

Adds:

- state before,
- state after,
- state deltas.

This is the preferred level.

### F4: decision-context trace

Adds:

- tools visible at decision time,
- model-visible local context,
- structured model output,
- host compaction events,
- policy resources active at the time.

This is highest fidelity.

Every package manifest should report the fidelity of source evidence.

---

## 10. Canonical event model

The event log should remain host-neutral.

A suggested envelope:

```json
{
  "schema_version": "jdsl.trace.v1",
  "event_id": "019c...",
  "capture_id": "cap_...",
  "episode_id": "ep_...",
  "sequence": 41,
  "timestamp": "2026-08-20T18:00:00.123Z",

  "source": {
    "host": "claude-code",
    "adapter": "claude-hooks",
    "model": "claude-..."
  },

  "actor": "model",
  "kind": "tool.call.started",

  "parent_event_id": "019c...",

  "payload": {
    "tool": {
      "logical_id": "retail.order.get",
      "host_name": "mcp__retail__get_order"
    },
    "arguments": {
      "order_id": "#W2378156"
    }
  },

  "state_before_ref": "sha256:...",
  "blob_refs": [],

  "prev_event_hash": "sha256:...",
  "event_hash": "sha256:..."
}
```

### 10.1 Event kinds

Start with a small set:

```text
capture.started
capture.finished

episode.started
episode.finished

user.message
assistant.message

model.requested
model.responded

toolset.exposed

tool.call.proposed
tool.call.started
tool.call.completed
tool.call.failed

state.snapshot
state.delta

environment.reward
environment.verdict

host.compaction
host.subagent.started
host.subagent.finished

annotation
```

Not every adapter emits every event.

### 10.2 Hash chain

Each event should include the previous event digest.

This gives you tamper evidence.

The compiler then has a stable provenance chain:

```text
source trajectory
-> candidate behavior
-> compiled node
-> verification report
```

### 10.3 Blob storage

Large content should not sit inside JSONL.

Examples:

- full database snapshots,
- screenshots,
- large tool outputs,
- source files,
- long transcripts.

Store these as content-addressed blobs:

```text
blobs/sha256/<digest>
```

Events reference the digest.

### 10.4 OpenTelemetry export

Do not make OpenTelemetry the canonical trace database.

Use a jdsl-native event model.

Add an OpenTelemetry exporter later.

OpenTelemetry already defines GenAI attributes around system instructions, tool-call IDs, arguments, results, usage, and related agent telemetry.[^otel-genai]

This gives jdsl interoperability with existing tracing systems while preserving richer compiler-specific lineage internally.

---

## 11. State tracking

Tool traces alone are not enough for good policy induction.

The compiler needs state.

### 11.1 Raw state vs semantic state

Keep two forms.

Raw state is authoritative environment evidence.

Examples:

```text
database dump
API object
filesystem tree
test output
browser DOM snapshot
```

Semantic state is normalized compiler input.

Example:

```json
{
  "authenticated": true,
  "customer_id": "U17",
  "target_order_id": "#W2378156",
  "order_status": "pending",
  "confirmation_state": "missing"
}
```

Never replace raw evidence with the semantic representation.

Keep both.

### 11.2 Environment adapter

Define a small interface:

```python
class EnvironmentAdapter(Protocol):
    async def snapshot(self) -> JSONValue | None: ...
    async def outcome(self) -> Outcome | None: ...
    def canonical_tool(self, host_tool: ToolIdentity) -> str: ...
```

Optional extensions:

```python
async def diff(before, after) -> JSONValue
async def observe_after(tool_call) -> JSONValue
```

The gateway invokes snapshots around state-changing operations when practical.

### 11.3 Append-only Timeline

Borrow Schema's strongest storage idea.

Maintain an immutable Timeline:

```text
observation
action
observation
action
observation
```

The compiler may revise interpretations.

The compiler must never revise history.

---

## 12. Tool contracts

Portable behavior requires portable tool meaning.

Host tool names are not enough.

`mcp__retail__get_order` is a host identifier.

The package needs a logical capability identifier.

Example:

```text
retail.customer.lookup
retail.order.list
retail.order.get
retail.order.cancel
```

A tool contract should contain:

```json
{
  "logical_id": "retail.order.cancel",
  "input_schema": {
    "type": "object",
    "properties": {
      "order_id": {"type": "string"}
    },
    "required": ["order_id"]
  },
  "output_schema": {
    "type": "object"
  },
  "effects": {
    "read_only": false,
    "destructive": true,
    "idempotent": false
  }
}
```

MCP already exposes structured schemas and tool annotations such as read-only, destructive, and idempotent hints.[^mcp-tools]

Treat third-party annotations as hints.

Verify critical properties through trusted tool definitions or environment contracts.

### 12.1 Runtime binding

A behavior package refers to:

```text
retail.order.cancel
```

At runtime, the host provides a binding:

```text
retail.order.cancel -> actual Python tool
```

or:

```text
retail.order.cancel -> MCP server X / tool cancel_order
```

If a required capability is missing, package loading fails before execution.

---

## 13. Normalization

Raw trajectories contain surface variation.

The compiler needs symbolic structure.

Example raw calls:

```text
lookup_customer(email="a@example.com")
lookup_customer(phone="+...")
lookup_customer(name="...")
```

A normalizer might map all three to:

```text
operation = resolve_customer
input_role = customer_identifier
output_role = customer
```

Keep the raw tool identity too.

### 13.1 Normalization stages

1. Canonicalize host event types.
2. Canonicalize tool identity.
3. Normalize structured arguments.
4. Identify exact value lineage.
5. Replace instance-specific values with symbolic variables.
6. Attach state before and after.
7. Group low-level events into action steps.
8. Mark outcome and policy violations.

### 13.2 Symbolic substitution

Teacher trajectory:

```text
lookup -> customer U17
list_orders(customer_id="U17")
orders -> #W2378156
get_order(order_id="#W2378156")
```

Normalized trajectory:

```text
lookup -> $customer
list_orders(customer_id=$customer.id)
list_orders -> $orders
select -> $target_order
get_order(order_id=$target_order.id)
```

This is the representation from which dataflow should be compiled.

---

## 14. Behavior mining

Do not ask one frontier model to read raw traces and emit final jdsl Python.

Use a staged mining process.

## 14.1 Stage A: local trace analysis

Analyze each trajectory independently.

Extract candidate facts such as:

```text
A preceded B.
Value X flowed from output A to argument B.
Error E was followed by recovery R.
The model selected among N candidate tools.
The model transformed language into enum C.
```

No generalization yet.

## 14.2 Stage B: cross-trace consolidation

Group equivalent local facts.

Measure:

- support,
- applicability count,
- counterexample count,
- successful outcomes,
- failed outcomes,
- environment states,
- tool versions.

### 14.2.1 Candidate behavior record

Example:

```json
{
  "candidate_id": "cand_flow_019",
  "type": "DATAFLOW",

  "claim": {
    "source": "$customer.id",
    "target": {
      "tool": "retail.order.list",
      "argument": "/customer_id"
    }
  },

  "evidence": {
    "applicable": 184,
    "support": 184,
    "counterexamples": 0,
    "episodes": ["ep_1", "ep_4", "ep_9"]
  },

  "status": "proposed"
}
```

## 14.3 Stage C: adversarial review

A second compiler pass should search for:

- counterexamples,
- hidden state differences,
- teacher quirks,
- version-specific behavior,
- spurious ordering,
- unnecessary model calls,
- unsafe overgeneralization.

This mirrors the useful consolidation idea in Trace2Skill, but the output is a behavior hypothesis graph rather than a text Skill.

---

## 15. Do not confuse teacher habit with policy

This is one of the hardest problems.

Suppose the teacher always calls `list_orders` before `get_order`.

That does not prove the sequence is required.

The teacher might simply prefer that route.

A compiler that turns every repeated habit into hard control will overfit.

Every candidate should carry an evidence grade.

Suggested grades:

### E0: observed

Seen once.

Never compile as a hard rule.

### E1: repeated

Seen across multiple applicable traces.

Useful candidate.

### E2: contrastive

Supported in positive cases and absent or different in meaningful negative cases.

Stronger.

### E3: contract-backed

Supported by trusted task policy, tool contract, environment schema, or explicit invariant.

Strong enough for guards and action restrictions.

### E4: replay-verified

The candidate reproduces historical routing or dataflow across all relevant source traces.

### E5: held-out validated

The rule succeeds on unseen tasks or environments.

For safety-sensitive or destructive actions, hard guards should generally require contract-backed or externally verified evidence.

Frequency alone is not enough.

---

## 16. Mining each behavior type

## 16.1 DATAFLOW mining

This should be mostly deterministic.

For each tool argument:

1. Search earlier structured outputs and state values.
2. Compare exact typed values.
3. Track JSON pointer paths.
4. Use blackboard provenance when running inside jdsl.
5. Record source-to-target lineage.

Example:

```text
tool A output /customer/id
==
tool B input /customer_id
```

Candidate:

```text
ref("customer.id")
```

This removes exact copying from the model.

This is where the `#W2378156` example belongs.

If the identifier already exists in trusted state, the model should not regenerate the identifier.

## 16.2 CONTROL mining

Build a normalized event graph.

Start with a prefix DAG or trajectory trie:

```text
auth
  -> list
      -> select
          -> get
              -> confirm
                  -> cancel
```

Factor common prefixes.

Then examine diverging paths against state.

Do not force every trace into one total order.

Preserve partial order where possible.

Current jdsl is sequence-oriented, so the first compiler may lower only behaviors that fit `seq`, `sel`, and bounded `repeat`.

Parallel behavior may stay out of the MVP.

## 16.3 GUARD mining

Use contrastive state sets.

Example:

Positive states before cancellation:

```text
confirmation_state = confirmed
order_status = pending
```

Negative states:

```text
confirmation_state = missing
confirmation_state = rejected
order_status = shipped
```

A frontier compiler model may propose:

```text
confirmation_state == confirmed
AND
order_status == pending
```

A deterministic verifier tests the proposal against all traces and trusted contracts.

Do not let the model's confidence become the guard.

## 16.4 ACTION mining

When a particular state maps consistently to a tool operation, propose fixed `act`.

Example:

```text
known target_order
+ confirmed cancellation
-> retail.order.cancel
```

Before staticizing, check:

- tool is stable,
- arguments have deterministic sources,
- no alternative successful action appears under equivalent state,
- operation semantics are trusted.

## 16.5 RECOVERY mining

Normalize errors.

Example:

```text
lookup_by_id -> not_found
then
list_account_orders -> success
```

Group by:

- error code,
- tool,
- state,
- next action.

Compile only recurrent recovery with bounded behavior.

Avoid unbounded retry.

## 16.6 SEMANTIC mining

Residual semantic decisions should be explicit.

Examples:

```text
transcript + orders -> selected_order_index
transcript -> requested_intent
user_message + pending_operation -> confirmation_state
```

These become small signatures.

---

## 17. Staticization pipeline

The compiler should attempt transformations in this order.

```text
1. Constant?
2. Exact dataflow?
3. Deterministic lookup?
4. Deterministic predicate?
5. Fixed tool operation?
6. Bounded known recovery?
7. Finite classification?
8. Residual model decision.
```

Pseudo-process:

```python
for decision in normalized_policy:
    if is_constant(decision):
        lower_constant(decision)

    elif has_exact_lineage(decision):
        lower_ref(decision)

    elif has_verified_predicate(decision):
        lower_guard(decision)

    elif has_verified_fixed_action(decision):
        lower_act(decision)

    elif has_verified_recovery(decision):
        lower_recovery(decision)

    else:
        residualize(decision)
```

The important part is the ordering.

Do not start by generating prompts.

Start by eliminating model decisions.

---

## 18. Residual signatures

A behavior package is not one signature.

The package contains many local signatures.

A signature is the typed interface between one tree leaf and the small model.

### 18.1 Example

```json
{
  "id": "resolve_target_order",
  "kind": "predict",

  "inputs": {
    "request": {
      "source": "blackboard.request",
      "schema": {"type": "string"}
    },
    "orders": {
      "source": "blackboard.orders",
      "schema": {"type": "array"}
    }
  },

  "output": {
    "name": "selected_index",
    "schema": {
      "type": "integer",
      "minimum": 0
    }
  },

  "instruction": "Choose the order the customer is referring to.",

  "context_policy": {
    "max_instruction_tokens": 160,
    "include_only": ["request", "orders"]
  },

  "validator": {
    "type": "json_schema"
  }
}
```

### 18.2 Signature rules for small models

Each residual signature should:

- have stable identity,
- receive only required fields,
- use typed outputs,
- prefer enums or indices,
- expose the smallest useful tool set,
- avoid unrelated policy text,
- avoid exact-value reproduction when refs exist,
- include few local examples,
- have a deterministic validator,
- have a bounded retry policy.

### 18.3 Prefer `predict` over `react`

For small models, a compiled package should prefer:

```text
predict -> deterministic act
```

over:

```text
react with many tools
```

Example:

Bad residual leaf:

```text
react("handle cancellation", tools=[15 tools])
```

Better:

```text
predict("request, orders -> selected_index")
act(get_order, ref(selected_order_id))
guard(...)
act(cancel_order, ref(selected_order_id))
```

Reserve `react` for decisions where dynamic tool chaining remains necessary.

---

## 19. Richer signatures without breaking the current API

Keep this valid:

```python
predict("message -> category")
```

Add a first-class representation:

```python
sig = Signature(
    id="classify_intent",
    inputs=...,
    output=...,
    instruction=...,
    examples=...,
    validator=...,
)
```

Then support:

```python
predict(sig)
```

The string syntax remains the authoring shorthand.

The package format uses the structured form.

---

## 20. Stable node identity

Compiled artifacts need node IDs that survive formatting and small tree edits.

Add optional IDs to nodes:

```python
predict("message -> category", id="intent")
react("request -> answer", tools=[...], id="answer")
act(cancel_order, ref("order_id"), id="cancel")
```

For nodes without user IDs, derive temporary runtime IDs from tree path.

Do not use tree path as the persistent package identity.

A compiler or package editor might insert a node and shift every path.

---

## 21. Behavior IR

Humans should keep authoring jdsl through Python combinators.

The compiler needs a serializable internal representation.

That representation should remain an implementation and distribution format, not the primary human DSL.

### 21.1 Example IR

```json
{
  "format": "jdsl.behavior.v1",
  "root": {
    "type": "sequence",
    "id": "cancel_flow",
    "children": [
      {
        "type": "action",
        "id": "resolve_customer",
        "tool": "retail.customer.lookup",
        "store": "customer"
      },
      {
        "type": "action",
        "id": "list_orders",
        "tool": "retail.order.list",
        "arguments": {
          "customer_id": {
            "ref": "customer.id"
          }
        },
        "store": "orders"
      },
      {
        "type": "predict",
        "id": "resolve_target",
        "signature": "resolve_target_order"
      },
      {
        "type": "action",
        "id": "get_order",
        "tool": "retail.order.get",
        "arguments": {
          "order_id": {
            "ref": "orders[$selected_index].id"
          }
        },
        "store": "order"
      },
      {
        "type": "guard",
        "id": "cancellable",
        "expression": {
          "in": [
            {"ref": "order.status"},
            ["pending", "processing"]
          ]
        }
      }
    ]
  }
}
```

### 21.2 Restricted guard language

Do not ship generated Python predicates by default.

Start with a small safe expression system:

```text
exists
eq
neq
in
lt
lte
gt
gte
and
or
not
```

Values come from:

- literals,
- refs,
- simple JSON paths.

This is enough for many policy guards.

For domain logic that exceeds the expression system, reference a trusted runtime capability:

```json
{
  "type": "guard_call",
  "predicate": "retail.policy.is_cancellable",
  "arguments": {...}
}
```

The package references the predicate.

The runtime supplies trusted code.

---

## 22. Behavior package format

Use a directory as the canonical development representation.

Use deterministic ZIP as transport.

Suggested extension:

```text
.jdsl
```

### 22.1 Unpacked structure

```text
retail-cancellation/
├── manifest.json
├── behavior.json
├── tools.json
├── provenance.json
│
├── signatures/
│   ├── resolve_target_order.json
│   ├── classify_confirmation.json
│   └── explain_result.json
│
├── contracts/
│   ├── invariants.json
│   └── postconditions.json
│
├── tests/
│   ├── replay.jsonl
│   ├── guards.jsonl
│   └── signatures.jsonl
│
├── evidence/
│   └── summary.json
│
└── README.md
```

Raw private traces should not ship by default.

Store evidence summaries and source digests.

### 22.2 Manifest

Example:

```json
{
  "format": "jdsl.package.v1",
  "name": "retail-cancellation",
  "version": "0.1.0",

  "runtime": {
    "jdsl": ">=0.2"
  },

  "task_family": "retail-support",

  "required_capabilities": [
    "retail.customer.lookup",
    "retail.order.list",
    "retail.order.get",
    "retail.order.cancel"
  ],

  "source": {
    "compiler": "jdsl-compiler",
    "compiler_model": "frontier-model-id",
    "capture_fidelity": "F3",
    "episode_count": 184
  },

  "verification": {
    "status": "passed",
    "replay_coverage": 1.0
  },

  "files": {
    "behavior.json": "sha256:..."
  }
}
```

### 22.3 No arbitrary code by default

Downloaded packages are executable policy.

Treat them like software.

Do not place arbitrary frontier-generated Python in the default package.

Start with:

- restricted IR,
- restricted expressions,
- declarative signatures,
- references to trusted external tools.

This keeps package review and sandboxing tractable.

### 22.4 Signing later

After package semantics stabilize, add optional artifact signing.

Sigstore Cosign supports signing ordinary files and blobs and recommends bundle-based signing metadata.[^sigstore]

A future registry may require signed package digests.

Do not make signing an MVP blocker.

---

## 23. Package provenance

Every compiled node should answer:

> Why does this node exist?

Example provenance:

```json
{
  "node_id": "cancel_after_confirmation",
  "behavior_candidate": "cand_guard_044",
  "evidence_grade": "E4",
  "source_episodes": [
    "sha256:...",
    "sha256:..."
  ],
  "contract_sources": [
    "policy:confirm-before-write:v1"
  ],
  "compiler_model": "..."
}
```

This makes packages auditable.

A developer inspecting a strange guard should be able to trace the guard back to source evidence.

---

## 24. Compiler architecture

The compiler should be a pipeline.

```text
raw captures
    |
    v
validate trace integrity
    |
    v
normalize
    |
    v
segment episodes
    |
    v
extract local behavior facts
    |
    v
consolidate across episodes
    |
    v
generate candidate behaviors
    |
    v
adversarial counterexample search
    |
    v
verify candidates
    |
    v
staticize
    |
    v
construct behavior IR
    |
    v
residualize semantic decisions
    |
    v
slice local context
    |
    v
replay
    |
    v
held-out evaluation
    |
    v
package
```

### 24.1 Model role

Use the frontier compiler model for:

- semantic grouping,
- candidate rule proposal,
- intent labeling,
- failure-mode clustering,
- decomposition proposals,
- counterexample hypotheses,
- residual signature wording.

Do not use the frontier model as the final authority for:

- exact dataflow,
- schema validity,
- support counts,
- guard truth on recorded states,
- package integrity,
- tool type checking,
- replay scores.

Those should be deterministic.

---

## 25. A concrete compiler strategy

### 25.1 Build a trajectory trie first

Given normalized successful trajectories:

```text
A B C D
A B C E
A B F
A G
```

Build:

```text
A
├── B
│   ├── C
│   │   ├── D
│   │   └── E
│   └── F
└── G
```

This gives the compiler an initial structural object without LLM-generated code.

### 25.2 Replace instance values with refs

Before branch induction:

```text
cancel_order("#W2378156")
```

becomes:

```text
cancel_order(ref(target_order.id))
```

### 25.3 Explain branches with state

For a branch:

```text
C -> D
C -> E
```

Compare state before the branch.

Ask the compiler model to propose a minimal state predicate.

Verify the predicate.

If verified:

```text
sel(
  seq(guard(P), D),
  E
)
```

If no reliable predicate exists:

```text
predict(local_state -> branch)
```

### 25.4 Merge equivalent states

Two different trace prefixes might arrive at equivalent state.

Merge those states when:

- required blackboard fields match,
- future valid action sets match,
- trusted policy state matches.

This prevents giant memorized tries.

### 25.5 Detect bounded loops

If a motif repeats:

```text
lookup -> transient_error
lookup -> transient_error
lookup -> success
```

and the environment or policy supports retry:

```text
repeat(lookup, until=success, max=N)
```

Do not infer unlimited loops.

### 25.6 Minimize

After lowering:

- remove redundant guards,
- collapse fixed selectors,
- remove unnecessary model leaves,
- prune unused blackboard fields,
- minimize local instruction text,
- reduce tool sets.

The compiler objective is not shortest tree.

The objective is lowest model burden while preserving verified behavior.

---

## 26. Iterative residual decomposition

A compiled signature might still be too hard for a 2B model.

Example:

```text
transcript + order + policy -> allowed_action
```

Do not immediately fine-tune.

Run a second compiler pass.

The frontier compiler asks:

> Which sub-decisions inside this residual leaf are deterministic or easier?

Possible rewrite:

```text
transcript -> requested_action       [small model]
order -> order_state                 [deterministic]
requested_action + order_state
    -> policy_key                    [deterministic mapping]
policy_key -> allowed_action         [deterministic lookup]
```

The residual model burden shrinks again.

This recursive decomposition is central to the jdsl thesis.

---

## 27. Schema-style prediction checks

This belongs after the MVP but should influence the data model now.

For a state-changing action, store an expected postcondition.

Example:

```json
{
  "tool": "retail.order.cancel",
  "precondition": {
    "eq": [
      {"ref": "confirmation.state"},
      "confirmed"
    ]
  },
  "postcondition": {
    "eq": [
      {"ref": "observed_order.status"},
      "cancelled"
    ]
  }
}
```

Runtime:

```text
predict expected state
-> execute action
-> observe
-> compare
```

On mismatch:

```text
invalidate dependent plan
-> recovery subtree
```

This imports Schema's evidence discipline into a reusable behavior policy.

---

## 28. MCP server design

The MCP server should remain small and stable.

### 28.1 Control tools

Suggested tool set:

```text
jdsl_capture_start
jdsl_capture_finish
jdsl_capture_mark_outcome
jdsl_capture_summary

jdsl_compile
jdsl_compile_status

jdsl_verify
jdsl_package_inspect
jdsl_package_export
```

MCP tool names should remain stable.

Use structured output schemas.

### 28.2 Resources

Optional MCP resources:

```text
jdsl://captures/{capture_id}/summary
jdsl://captures/{capture_id}/report
jdsl://packages/{package_id}/manifest
jdsl://packages/{package_id}/verification
```

Large raw traces should stay out of model context unless explicitly requested.

### 28.3 Prompts

MCP prompt primitives are optional.

Do not make compiler correctness depend on a host invoking a specific prompt template.

Keep compiler prompts server-side.

### 28.4 Long-running compile

If the client supports MCP tasks, expose compile and verification as task-capable operations.[^mcp-tasks]

Otherwise return an explicit compiler job handle.

The protocol transport should not define job identity.

---

## 29. Host plugin packaging

The "jdsl plugin" should be a thin host shim around one common harness.

### 29.1 Claude Code package

Contents:

```text
jdsl-claude-plugin/
├── plugin metadata
├── MCP configuration
├── hooks/
│   ├── session-start
│   ├── pre-tool
│   ├── post-tool
│   ├── post-tool-failure
│   └── session-end
└── scripts/
    └── jdsl-hook-forwarder
```

The hook forwarder:

1. reads Claude's structured JSON from stdin,
2. maps host event to jdsl canonical event,
3. writes to local ingest,
4. emits valid hook output,
5. exits quickly.

Claude Code already exposes the relevant structured hook events.[^claude-hooks]

### 29.2 Gemini CLI extension

Contents:

```text
jdsl-gemini-extension/
├── MCP server configuration
├── hooks
└── forwarder
```

Gemini's hook API offers even more capture points, including model and tool-selection events.[^gemini-hooks-ref]

Start with:

```text
SessionStart
BeforeAgent
BeforeToolSelection
BeforeTool
AfterTool
AfterAgent
SessionEnd
```

Do not store full model requests by default.

### 29.3 Generic MCP host

If a host supports MCP but not hooks:

```text
install jdsl MCP
use jdsl-proxied task tools
```

The plugin gets full visibility over tools routed through jdsl.

The plugin does not claim visibility over other host-native tools.

### 29.4 Custom agent SDK

Offer an SDK adapter:

```python
with jdsl_capture(...) as cap:
    agent.run(...)
```

The adapter wraps:

- model calls,
- tool calls,
- environment observers,
- task outcome.

This should produce the highest-fidelity traces for benchmark research.

---

## 30. Storage design

Use boring storage first.

### MVP

- SQLite for metadata.
- JSONL for append-only event streams.
- Filesystem content-addressed blobs.
- SQLite WAL mode for concurrent readers.

Suggested tables:

```text
captures
episodes
event_index
blobs
tool_contracts
behavior_candidates
candidate_evidence
compiler_runs
packages
verification_runs
```

The source of truth for raw execution remains append-only events and blobs.

Derived compiler tables may be rebuilt.

### Later

Move to:

- Postgres,
- object storage,
- remote artifact registry,

only after scale requires the change.

Do not start with a vector database.

Most initial mining operates over structured traces.

---

## 31. Privacy and capture modes

The harness may see:

- source code,
- customer data,
- API outputs,
- emails,
- database identifiers,
- secrets.

Privacy must be part of the trace design.

### 31.1 Capture modes

#### Minimal

Store:

- event type,
- logical tool identity,
- schemas,
- argument/result hashes,
- state hashes,
- success/error class.

Useful for telemetry.

Weak for semantic mining.

#### Standard

Store:

- structured arguments,
- structured results,
- user/model surface messages needed for task semantics,
- redacted sensitive values.

Recommended default for behavior mining.

#### Full

Store:

- complete visible messages,
- tool definitions,
- broader host context,
- selected environment snapshots.

Explicit opt-in.

### 31.2 Redaction

Redact before durable persistence when possible.

Support:

- secret pattern detection,
- configurable JSON paths,
- tool-specific redactors,
- field hashing,
- reversible local vault references if required.

Do not upload secrets to a compiler model merely because the trace contains them.

### 31.3 No hidden reasoning collection

Do not make private reasoning part of the format.

Behavior transfer should work from observable execution.

That keeps the architecture model-provider-neutral.

---

## 32. Verification

Compilation without verification will produce fragile policies.

Verification should have several layers.

## 32.1 Structural verification

Check:

- package schema valid,
- every ref resolves,
- every required tool bound,
- tool arguments match schema,
- residual signature input fields exist,
- outputs have validators,
- loops are bounded,
- node IDs unique,
- no forbidden node type,
- package digest matches manifest.

## 32.2 Trace replay verification

Replay deterministic parts against historical traces.

Ask:

- Would the same dataflow refs resolve?
- Would each guard choose the observed branch?
- Would fixed actions be legal in the recorded state?
- Would recovery activate on the recorded error?
- Does a residual leaf receive enough information to reproduce the historical branch?

Record coverage.

## 32.3 Counterexample verification

For each proposed guard or action rule, search:

- failed trajectories,
- successful alternate trajectories,
- nearby states,
- policy docs,
- tool contracts.

A rule with one contradictory valid example should not become a hard invariant without an explanation.

## 32.4 Residual signature unit tests

Each residual signature gets a small dataset:

```text
input -> expected output class
```

Run the target small model directly on the leaf.

This gives per-leaf failure localization.

## 32.5 Held-out live verification

Final evidence should come from unseen tasks.

Do not report source-trace replay as task success.

## 32.6 Cross-model verification

Run the same package with at least two smaller model families.

If both improve, the result better supports portable behavior transfer rather than model-specific prompt tuning.

---

## 33. Metrics

Final pass rate is necessary.

Final pass rate is not enough.

Track:

### Task success

```text
pass rate
pass^k
environment reward
```

### Residual Decision Burden

```text
model-dependent decisions / meaningful decisions
```

### Deterministic Coverage

```text
compiled deterministic decisions / meaningful decisions
```

Break down by:

- control,
- dataflow,
- guards,
- actions,
- recovery.

### Active Policy Tokens

Average instruction tokens visible to the model per leaf call.

### Visible Tool Branching Factor

Average number of tools exposed per model decision.

### Exact Dataflow Rate

Fraction of later arguments supplied by deterministic refs rather than model regeneration.

### Invalid Tool Call Rate

Wrong tool or schema-invalid call rate.

### Policy Violation Rate

Hard invariant violations per episode.

### Recovery Efficiency

Steps and model calls spent after tool failures.

### Package Portability

Performance delta from the same `.jdsl` across different small models.

### Compiler Amortization

Track:

- frontier episodes used to build package,
- frontier tokens spent compiling,
- downstream episodes run with package,
- runtime token reduction.

This gives the economic case.

---

## 34. The first benchmark experiment

Start narrow.

A good first target is one retail workflow with deterministic tools and clear environment state.

Cancellation is a reasonable example.

Pin one benchmark revision.

Do not mix versions.

### 34.1 Source data

Use:

- task policy,
- tool schemas,
- all available training tasks for the chosen workflow,
- frontier-model trajectories,
- environment outcome,
- state before and after writes.

Capture successful and failed runs.

Do not discard failed runs.

Failed runs provide counterexamples and valid local behavior.

### 34.2 Experimental arms

Keep the small model fixed.

Run:

#### A. Raw agent

Small model with normal tools.

#### B. Text Skill

Small model with a conventional procedural Skill.

#### C. Human jdsl

Small model with a hand-written tree.

#### D. Frontier-compiled jdsl

Same small model with the compiled behavior package.

#### E. Frontier model

Upper reference.

### 34.3 Stronger portability test

Repeat arm D with another small model family.

Do not recompile the package.

### 34.4 Success criteria

The important result is not "small model equals frontier model."

The first result to seek is:

```text
compiled package + frozen small model
>
text Skill + same frozen small model
```

and:

```text
compiled package + frozen small model
>
raw same frozen small model
```

while showing:

```text
lower active policy tokens
lower tool branching factor
lower residual decision burden
```

The strongest result is positive lift across multiple small-model families using the same package.

---

## 35. The first implementation sequence

Build the system in this order.

### PR 1: TraceSink in jdsl core

Add:

```python
class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None: ...
```

Add `trace_sink` to `RunContext`.

Default:

```text
NullTraceSink
```

Existing behavior remains unchanged.

Emit:

```text
node.enter
node.exit
blackboard.write
```

### PR 2: full `react` instrumentation

Record:

```text
react.started
model.requested
model.responded
toolset.exposed
tool.call.started
tool.call.completed
tool.call.failed
react.finished
```

This closes the largest trace gap in the current runtime.

### PR 3: stable node IDs

Add optional IDs to all nodes.

Render IDs in `jdsl show`.

### PR 4: canonical trace package

Add:

```text
jdsl/trace/
  events.py
  sink.py
  jsonl.py
  blobs.py
  replay.py
  redaction.py
```

Add deterministic event serialization.

### PR 5: MCP proxy / tool gateway

Add:

```text
jdsl/harness/
  gateway.py
  mcp_proxy.py
  capture.py
  state.py
```

Support upstream MCP tools.

Preserve tool schemas.

Record calls.

### PR 6: harness daemon

Add local service:

```text
MCP control endpoint
HTTP or Unix ingest endpoint
SQLite metadata
blob store
```

### PR 7: Claude and Gemini adapters

Ship thin adapters that translate host hooks into canonical events.

### PR 8: deterministic normalizer

Implement:

- tool canonicalization,
- exact data lineage,
- symbolic refs,
- error normalization,
- trajectory segmentation.

No LLM needed yet.

### PR 9: behavior candidate store

Implement the six atom types.

Add evidence support and counterexample counts.

### PR 10: first compiler model pass

Use structured output.

Compiler model proposes:

- semantic groupings,
- candidate guards,
- recovery clusters,
- residual signatures.

The model does not emit final Python.

### PR 11: Behavior IR and loader

Add:

```text
jdsl/ir/
  schema.py
  validate.py
  lower.py
```

Lower IR into existing `Node` classes.

### PR 12: verifier

Add:

- structural checks,
- replay,
- candidate evidence checks,
- path coverage,
- signature fixtures.

### PR 13: package export

Add:

```text
jdsl/package/
  manifest.py
  export.py
  load.py
```

Support `.jdsl`.

### PR 14: benchmark harness

Run the first fixed-weight small-model comparison.

Only after this point decide whether automatic topology induction deserves more investment.

---

## 36. Proposed repository layout

Keep the core small.

One practical first layout:

```text
jdsl/
├── dsl.py
├── tree.py
├── context.py
├── provider.py
│
├── trace/
│   ├── events.py
│   ├── sink.py
│   ├── jsonl.py
│   ├── blobs.py
│   ├── replay.py
│   └── redaction.py
│
├── ir/
│   ├── schema.py
│   ├── validate.py
│   └── lower.py
│
├── package/
│   ├── manifest.py
│   ├── load.py
│   └── export.py
│
└── cli.py

jdsl_harness/
├── server.py
├── capture.py
├── gateway.py
├── mcp_proxy.py
├── store.py
├── state.py
│
├── adapters/
│   ├── claude_code.py
│   ├── gemini_cli.py
│   ├── generic_mcp.py
│   └── import_jsonl.py
│
└── compiler/
    ├── normalize.py
    ├── lineage.py
    ├── candidates.py
    ├── consolidate.py
    ├── model.py
    ├── staticize.py
    ├── residualize.py
    ├── verify.py
    └── package.py
```

Keeping `jdsl_harness` separate protects the dependency-light core.

The current `jdsl` package has only a small dependency set.[^jdsl-pyproject]

The harness will likely add:

- MCP SDK,
- HTTP server,
- structured validation,
- database support,
- compiler-provider clients,
- optional telemetry libraries.

A separate package or optional dependency group keeps the interpreter light.

---

## 37. Proposed CLI

Runtime commands stay.

Add:

```bash
jdsl harness serve

jdsl capture list
jdsl capture inspect <id>

jdsl compile <capture-set>
jdsl compile inspect <run-id>

jdsl package verify <path>
jdsl package inspect <path>
jdsl package run <path> --model <model>

jdsl proxy list
jdsl proxy add ...
```

Host setup:

```bash
jdsl plugin install claude-code
jdsl plugin install gemini-cli
```

The installer should write host configuration only after user review.

---

## 38. Compiler prompts and model roles

The compiler should use structured calls.

Avoid one huge "write a tree" prompt.

Suggested roles:

### Trace analyst

Input:

- one normalized trajectory,
- state transitions,
- outcome.

Output:

- local behavior facts.

### Consolidator

Input:

- local facts across many traces.

Output:

- candidate behavior groups.

### Skeptic

Input:

- candidate,
- supporting traces,
- contradicting traces.

Output:

- possible failure conditions,
- missing state variables,
- overgeneralization risks.

### Decomposer

Input:

- a residual signature that performs poorly on the small model.

Output:

- possible deterministic substructure.

### Wording optimizer

Input:

- verified residual signature contract.

Output:

- concise leaf instruction and examples.

Only the final role should optimize text.

---

## 39. Structured compiler output

Example candidate proposal schema:

```json
{
  "type": "GUARD",
  "name": "confirmation_required_before_cancel",
  "scope": {
    "before_tool": "retail.order.cancel"
  },
  "predicate": {
    "eq": [
      {"ref": "confirmation.state"},
      "confirmed"
    ]
  },
  "evidence_needed": [
    "positive cancellation states",
    "negative unconfirmed states",
    "policy contract"
  ],
  "rationale_summary": "Cancellation appears only after matching confirmation."
}
```

The deterministic verifier then decides whether evidence supports the proposal.

Do not persist free-form model rationale as authority.

---

## 40. Small-model runtime behavior

At runtime:

```text
load package
-> validate manifest
-> bind capabilities
-> validate signatures
-> create blackboard
-> execute tree
```

When the tree reaches a model leaf:

```text
resolve required refs
-> render only local instruction
-> expose only local tools
-> call small model
-> validate typed output
-> write output to blackboard
-> continue tree
```

The small model never reads `behavior.json`.

The small model never reads the full package.

The runtime enforces the package.

This is the central product difference from text Skills.

---

## 41. Context slicing

Every residual signature should declare exactly what enters context.

Example:

```json
{
  "include": [
    "request",
    "orders"
  ],
  "exclude": [
    "authentication_policy",
    "tool_history",
    "unrelated_orders"
  ]
}
```

The compiler should measure field necessity.

A later minimizer may run ablations:

```text
remove field
-> signature still succeeds?
```

If yes, remove the field.

Context minimization should be empirical.

---

## 42. Tool-space slicing

Do the same with tools.

For every residual model leaf, compute the smallest tool set that preserves successful behavior.

A leaf that only selects an order should receive zero tools.

A leaf that needs one read operation should receive one read tool.

Do not expose writes before confirmation.

The package should represent tool visibility as policy, not prompt advice.

---

## 43. Hard invariants vs learned habits

Keep this distinction explicit in package metadata.

### Invariant

Must always hold.

Source:

- human policy,
- tool contract,
- verified safety requirement.

Example:

```text
confirm before destructive write
```

### Compiled heuristic

Observed to work and verified over current evidence.

Example:

```text
after not_found, enumerate account orders
```

Heuristics should have:

- confidence,
- fallback,
- package version,
- evidence.

Do not label heuristics as guarantees.

---

## 44. Failure modes to design against

### 44.1 Trace memorization

Compiler creates one giant tree matching source episodes.

Mitigation:

- symbolic refs,
- state abstraction,
- held-out validation,
- complexity penalties,
- merge equivalent states.

### 44.2 Teacher quirk compilation

Teacher's preference becomes hard policy.

Mitigation:

- contract evidence,
- alternate successful traces,
- counterexample search.

### 44.3 Wrong semantic normalization

Two tools get grouped as equivalent when semantics differ.

Mitigation:

- tool contracts,
- schema comparison,
- user overrides,
- namespace-aware logical IDs.

### 44.4 Unsafe staticization

A model decision becomes a fixed action even though hidden context matters.

Mitigation:

- conservative evidence thresholds,
- keep uncertain decisions residual,
- state completeness checks.

### 44.5 Too many residual leaves

The compiler produces a fragmented tree with many model calls.

Mitigation:

- merge closely related semantic leaves when total burden drops,
- measure calls and active context,
- optimize the whole package, not node count.

### 44.6 Too much deterministic structure

A brittle tree rejects legitimate novel paths.

Mitigation:

- explicit fallback subtree,
- confidence-aware heuristics,
- held-out tests,
- package versioning.

### 44.7 Package prompt injection

A downloaded package contains hostile instructions.

Mitigation:

- package signing,
- reviewable signatures,
- no arbitrary code,
- separate trusted invariants from untrusted text.

### 44.8 Host capture gaps

Plugin assumes it saw every action.

Mitigation:

- capture-fidelity field,
- gap events,
- gateway mode for high-confidence compilation.

---

## 45. Security model

Treat a `.jdsl` like an executable workflow.

### Loader rules

Reject packages with:

- unknown node types,
- unbound tool capabilities,
- undeclared network dependencies,
- invalid digests,
- unbounded repeats,
- malformed refs,
- arbitrary embedded Python,
- unsupported schema versions.

### Capability permissions

At install or run time, display:

```text
Reads:
- retail.customer.lookup
- retail.order.get

Writes:
- retail.order.cancel
```

Require explicit permission for destructive capability bindings.

### Compiler isolation

Compiler models receive only redacted source material required for the current analysis.

### Provenance

Manifest records:

- compiler version,
- source trace digests,
- model identity,
- verification status.

---

## 46. Testing strategy

### Core runtime tests

Add tests for:

- stable node IDs,
- event order,
- trace sink failure behavior,
- blackboard lineage,
- react tool trace,
- guard expressions,
- package lowering.

### Golden trace tests

Store small deterministic fixture trajectories.

Expected:

```text
trace -> candidate behavior -> IR
```

Version these.

### Property tests

Test:

- event serialization round trip,
- ref resolution,
- guard expression safety,
- deterministic ZIP hashes.

### Fuzz package loader

Feed malformed packages.

Loader must reject safely.

### Hook fixture tests

Use recorded Claude/Gemini hook payload examples.

Test normalization without running the hosts.

### End-to-end fixture

Create a tiny fake retail environment.

Teacher behavior:

```text
auth -> lookup -> confirm -> write
```

Compiler should remove:

- exact ID copying,
- fixed sequence,
- write gating.

Small fake model only handles one classifier.

This becomes CI.

---

## 47. What not to build first

Do not start with:

- fine-tuning,
- LoRA,
- topology induction from arbitrary domains,
- a public registry,
- visual package editor,
- arbitrary Python generation,
- full world-model induction,
- vector memory,
- autonomous package self-modification,
- separate adapter per leaf,
- model-specific package variants.

First prove:

> verified executable behavior extracted from frontier traces improves a frozen smaller model.

Everything else follows only if that result holds.

---

## 48. MVP definition

The MVP is complete when all of these work:

1. A frontier model solves tasks through jdsl capture.
2. Tool calls and results appear in canonical JSONL.
3. Exact data lineage is extracted.
4. Repeated sequences and failures produce behavior candidates.
5. A compiler model proposes semantic groupings and guards.
6. Deterministic verification accepts or rejects candidates.
7. Accepted candidates lower into Behavior IR.
8. Residual decisions become typed signatures.
9. The IR loads into the existing jdsl runtime.
10. A `.jdsl` exports.
11. A frozen small model runs the package.
12. The same package runs with a second small model.
13. Evaluation compares against raw and text-Skill baselines.

---

## 49. A first package example

Imagine source frontier traces show:

```text
user asks to cancel
lookup customer
list orders
identify target
fetch order
ask confirmation
cancel
verify
reply
```

Compiler output:

```text
CONTROL
authenticate before account access

DATAFLOW
customer.id -> list_orders.customer_id

SEMANTIC
request + orders -> selected_index

DATAFLOW
orders[selected_index].id -> get_order.order_id

GUARD
order.status is cancellable

CONTROL
confirmation before cancel

SEMANTIC
user reply + pending operation -> confirmation enum

DATAFLOW
target_order.id -> cancel_order.order_id

ACTION
cancel_order after guard

ACTION
get_order after cancel for verification

SEMANTIC
request + verified result -> reply
```

Compiled tree:

```text
seq(
  act(resolve_customer),
  store(..., "customer"),

  act(list_orders, ref("customer.id")),
  store(..., "orders"),

  predict(resolve_target_order),

  act(get_order, ref("orders[$selected_index].id")),
  store(..., "order"),

  guard(cancellable),

  act(request_confirmation),

  predict(classify_confirmation),

  guard(confirmation_matches_pending_operation),

  act(cancel_order, ref("order.id")),

  act(get_order, ref("order.id")),
  store(..., "verified_order"),

  guard(status_is_cancelled),

  predict(explain_result),
)
```

The small model does not:

- decide when to authenticate,
- decide which lookup tool follows,
- copy customer ID,
- copy order ID,
- decide whether confirmation gates the write,
- decide when to verify.

The small model does:

- resolve ambiguous language,
- classify confirmation,
- phrase the final response.

That is the behavior-transfer target.

---

## 50. Research questions worth measuring later

### How much behavior is staticizable?

Measure by domain.

Tool-heavy transactional tasks may staticize well.

Open-ended research tasks may leave larger residuals.

### How does package performance scale with teacher diversity?

Compare:

- one frontier model,
- several frontier models,
- successful traces only,
- successful plus failed traces.

### Does cross-model compilation help?

A package extracted from one teacher should run with multiple student model families.

### Does compiler sophistication matter?

Compare:

- frequency rules,
- one-model compiler,
- analyst/consolidator/skeptic compiler,
- human-reviewed compiler.

### How small may the student become?

Plot performance against student model size while holding package fixed.

### Which artifact transfers best?

Compare:

- raw trajectories,
- textual Skill,
- retrieved Skill fragments,
- compiled jdsl package,
- compiled package plus text leaf examples.

This is the key scientific comparison.

---

## 51. Recommended first build decision

Start with the tracing and gateway layer.

Do not start with package formatting.

The package format will become obvious after the compiler produces stable IR.

The first concrete milestone should be:

```text
frontier host
-> jdsl capture
-> canonical trace
-> exact lineage report
```

Example output:

```text
Episode ep_42

9 tool calls
3 state changes
4 exact cross-call value flows
2 retries
1 ambiguous semantic decision

Deterministic candidates:
- customer.id -> list_orders.customer_id
- target_order.id -> get_order.order_id
- target_order.id -> cancel_order.order_id
- get_order precedes cancel_order

Residual candidates:
- request + orders -> selected order
```

If jdsl produces this report reliably across Claude and Gemini traces, the hardest foundation is in place.

Then build the compiler.

---

## 52. Recommended product statement

A concise technical description:

> jdsl extracts observable task behavior from frontier-agent trajectories, verifies reusable structure against execution evidence, and compiles that structure into portable behavior packages. Packages move sequencing, state, dataflow, guards, tool scope, and recovery outside the language model, leaving small local signatures for frozen models to solve at runtime.

A shorter research statement:

> Compile frontier-model behavior into executable policy so weaker frozen models have less policy to infer.

---

## 53. Final recommendation

Build the harness around five principles.

### 1. Observe actions, not hidden reasoning

Tool calls, arguments, state, results, failures, and outcomes form the evidence base.

### 2. Use MCP for control and proxying, not as the only telemetry channel

MCP gives jdsl broad host reach.

Fast local event ingest gives the compiler complete traces without turning logging into model work.

### 3. Treat the frontier model as a hypothesis generator

The model proposes abstractions.

Recorded evidence, schemas, contracts, replay, and held-out tasks decide what survives.

### 4. Compile away model responsibility

Exact dataflow, fixed sequencing, known guards, deterministic tools, and bounded recovery belong in jdsl structure.

Text stays only where semantic judgment remains.

### 5. Make the package executable, inspectable, and portable

The package should expose:

- what is deterministic,
- what still calls a model,
- which capabilities are required,
- why each rule exists,
- which traces support the rule,
- which tests the package passed.

If this architecture works, jdsl is not another Agent Skills format.

jdsl becomes a behavior compiler and runtime.

The frontier model pays the cost of interpreting and organizing complex procedure during capture and compilation.

The smaller model receives only the remaining local decisions during execution.

That is the experiment worth building.

---

## References

[^jdsl]: Cantor Industries, `jdsl-py`, current repository. https://github.com/Cantor-Industries/jdsl-py

[^jdsl-tree]: `jdsl/tree.py`, current runtime implementation. https://github.com/Cantor-Industries/jdsl-py/blob/master/jdsl/tree.py

[^jdsl-context]: `jdsl/context.py`, current blackboard and run-context implementation. https://github.com/Cantor-Industries/jdsl-py/blob/master/jdsl/context.py

[^jdsl-pyproject]: `pyproject.toml`, current package metadata and dependencies. https://github.com/Cantor-Industries/jdsl-py/blob/master/pyproject.toml

[^skills-anthropic]: Anthropic, Agent Skills overview and engineering description. https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview and https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills

[^skillsbench]: Li et al., "SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks", arXiv:2602.12670, 2026. https://arxiv.org/abs/2602.12670

[^trace2skill]: Ni et al., "Trace2Skill: Distill Trajectory-Local Lessons into Transferable Agent Skills", arXiv:2603.25158, 2026. https://arxiv.org/abs/2603.25158 and official implementation https://github.com/Qwen-Applications/Trace2Skill

[^skillx]: Wang et al., "SkillX: Automatically Constructing Skill Knowledge Bases for Agents", arXiv:2604.04804, 2026. https://arxiv.org/abs/2604.04804

[^schema]: Schema Harness project page. Results shown there are project-reported public-set results. https://schema-harness.github.io/

[^schema-traces]: Schema Harness public ARC-AGI-3 trace dataset. https://huggingface.co/datasets/schema-harness/arc-agi-3-schema-traces

[^claude-hooks]: Anthropic, Claude Code hooks guide and reference. https://code.claude.com/docs/en/hooks-guide and https://code.claude.com/docs/en/hooks

[^gemini-hooks]: Gemini CLI hooks overview. https://geminicli.com/docs/hooks/

[^gemini-hooks-ref]: Gemini CLI hooks reference. https://geminicli.com/docs/hooks/reference/

[^mcp-tools]: Model Context Protocol tool schema and tool execution specification. https://modelcontextprotocol.io/specification/2025-11-25/server/tools

[^mcp-tasks]: Model Context Protocol task utility. https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks

[^otel-genai]: OpenTelemetry GenAI semantic conventions and attribute registry. https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/

[^sigstore]: Sigstore, signing ordinary files and blobs with Cosign. https://docs.sigstore.dev/cosign/signing/signing_with_blobs/