# Compiler Pipeline

The compiler turns canonical traces into Behavior IR. It is conservative: if a
claim cannot be represented and verified from evidence, it should stay out of
deterministic policy.

## Inputs

The compiler consumes `Episode` objects from `jdsl.trace.replay`. Episodes are
usually created by:

- jdsl-native runtime tracing
- `ToolGateway`
- MCP proxy recording
- host hook adapters
- imported JSONL logs

Each episode is an ordered event stream with tool calls, model events,
blackboard writes, and optional outcomes.

## Normalize

`jdsl_harness.compiler.normalize` converts each episode into a `NormEpisode`.

For every tool call it records:

- step index
- logical tool id
- host tool name
- arguments
- result or error
- blackboard store name
- argument lineage

Lineage is exact. If a later argument equals a meaningful value from prior
trusted state, the normalizer records the source path. Example:

```text
customer.id -> list_orders.customer_id
orders[1].id -> get_order.order_id
```

## Consolidate

`consolidate` turns per-episode facts into behavior candidates. Candidates carry
support, counterexamples, source episodes, and an evidence grade.

The main candidate families are:

| Family | Meaning |
| --- | --- |
| `DATAFLOW` | exact value movement from earlier state into later arguments |
| `ACTION` | a tool call that appears in the successful skeleton |
| `GUARD` | a state predicate that should gate a call |
| `RECOVERY` | a failure-to-recovery relation |
| `SEMANTIC` | a decision slot still requiring model judgment |

## Staticize

`staticize` chooses the modal successful tool sequence and emits Behavior IR.

For every action argument it chooses one representation:

| Representation | When used |
| --- | --- |
| `{"ref": "path"}` | exact dataflow explains the value |
| `{"ref": "input_name"}` | unlinked argument varies across episodes |
| `{"const": value}` | unlinked argument is invariant across episodes |

Observed residual decisions are emitted as typed signatures and `predict` or
`react` IR leaves.

## Verify

Verification checks two things:

1. structural validity of the IR
2. replay coverage of deterministic refs and guards against source traces

The package loader repeats structural checks and verifies file digests before
binding tools.

## Package

`build_package` creates a `BehaviorPackage`:

- `manifest.json`
- `behavior.json`
- `tools.json`
- `signatures/*.json`
- `provenance.json`
- optional replay/signature evidence

`export_jdsl` writes a deterministic zip archive with the `.jdsl` extension.

## Metrics

The core static metrics are:

- `residual_decision_burden`
- `deterministic_coverage`
- `exact_dataflow_rate`
- `visible_tool_branching_factor`
- `active_policy_tokens`

`active_policy_tokens` is currently a structural approximation based on
instruction text splitting. Runtime telemetry is needed for true tokenizer
counts and latency attribution.
