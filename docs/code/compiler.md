# Compiler Internals

The compiler is implemented under
[`jdsl_harness/compiler/`](https://github.com/Cantor-Industries/jdsl-py/tree/harness/jdsl_harness/compiler).
It is not a prompt-to-code generator. It is a deterministic evidence pipeline
that turns canonical trace episodes into restricted Behavior IR.

The top-level entry point is
[`compile_behavior`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/compiler/package.py):

```text
Episode[]
  -> normalize_all
  -> consolidate
  -> staticize
  -> verify
  -> build_package
```

The optional compiler model is used only for residual signature naming and
wording. Structure, support counts, refs, replay checks, package manifests, and
digests are produced by ordinary Python.

## 1. Normalize

[`normalize.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/compiler/normalize.py)
converts a replayed `Episode` into a `NormEpisode`.

The normalizer walks events in sequence order and maintains a trusted state map.
`blackboard.write` updates that map. `tool.call.started` creates a `NormStep`.
`tool.call.completed` attaches the result to that step and stores it under either
the explicit `store` name from the runtime or a synthesized name such as
`list_orders_out_1`.

Each `NormStep` records:

| Field | Why it matters |
| --- | --- |
| `logical_tool` | The portable capability id the package will later require. |
| `host_tool` | The host-visible tool name seen in the trace. |
| `arguments` | The actual arguments used in that episode. |
| `arg_lineage` | For each argument, the prior state path that exactly produced it. |
| `state_before` | Snapshot of trusted state at call time for replay verification. |
| `store` | The blackboard key where the tool result is available to later refs. |

Model decisions are recorded separately as `ModelDecision`. A `predict` is
detected from a `node.enter` event whose node type is `predict`; a `react` is
detected from `react.started`. Those decisions become residual signatures later.

## 2. Exact Lineage

[`lineage.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/compiler/lineage.py)
is the main reason compiled behavior can shrink model responsibility.

When a later tool argument is exactly equal to a meaningful value already in
trusted state, the compiler records a path:

```text
customer.id -> list_orders.customer_id
orders[$selected_index].id -> get_order.order_id
```

The match is intentionally strict:

- trivial values such as `None`, booleans, empty strings, `0`, `1`, and `-1` are
  ignored to avoid false matches
- strings must have at least two characters
- bools do not equal numbers
- nested dict/list paths are searched up to a bounded depth

The symbolic index form is important. If the model wrote `selected_index = 1`
and the tool later used `orders[1].id`, lineage can prefer
`orders[$selected_index].id`. The compiled package then asks the model only for
the index, and deterministic code copies the actual id.

## 3. Candidate Extraction

[`candidates.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/compiler/candidates.py)
extracts local facts from one normalized episode. The current atom families are:

| Atom | Meaning |
| --- | --- |
| `DATAFLOW` | A tool argument came from an exact prior state path. |
| `CONTROL` | One successful tool call immediately preceded another. |
| `ACTION` | A successful tool call happened with a given ref-argument shape. |
| `RECOVERY` | A failed tool call was followed by a different successful tool. |
| `SEMANTIC` | A model decision remained visible in the trace. |

This stage does not generalize across examples. It only says, for this one
episode, what was observed.

## 4. Consolidation

[`consolidate.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/compiler/consolidate.py)
groups equivalent facts across episodes and assigns conservative evidence.

The important rule is applicability. A missing fact is a counterexample only
when the claim could have applied in that episode. For example, a dataflow claim
for `list_orders.customer_id` applies only to episodes that actually called
`list_orders` with a `customer_id` argument.

Evidence grades used today:

| Grade | Meaning in the implementation |
| --- | --- |
| `E0` | Single weak proposal, not enough to trust as a hard rule. |
| `E1` | Repeated uncontested support, still weak. |
| `E2` | At least three uncontested supports. |
| `E3` | Contract-backed claim supplied by trusted metadata. |
| `E4` | Replay-verified claim after deterministic checks pass. |

If there is a counterexample, the candidate becomes `contested`. Contested facts
can remain in reports, but they should not become hard deterministic policy.

## 5. Staticization

[`staticize.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/compiler/staticize.py)
builds Behavior IR.

First it chooses a control skeleton: the modal successful tool sequence. Then it
walks the representative episode and emits nodes in order:

1. residual model decisions observed before the next tool
2. verified guards before that tool
3. an action for the tool itself
4. optional recovery wrapping when accepted recovery evidence exists

For every action argument, staticization chooses one representation:

| Representation | When used |
| --- | --- |
| `{"ref": "path"}` | Exact dataflow explains the value. |
| `{"ref": "input_name"}` | The argument varies across episodes and no dataflow explains it. |
| `{"const": value}` | The argument is invariant across episodes. |

Repeated calls to the same tool are position-sensitive. `bash.command` at step 0
and `bash.command` at step 1 are different call slots, so they do not collapse
into one ambiguous runtime input.

## 6. Residual Signatures

[`residualize.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/compiler/residualize.py)
turns `ModelDecision` records into typed `Signature` objects plus an IR
`predict` or `react` leaf.

This is the compiler's bias:

```text
prefer deterministic refs, guards, and actions
then leave only genuine judgment as a model signature
```

For the retail cancellation fixture, the desired residual is
`request, orders -> selected_index`. The model picks which order the user meant;
the runtime then resolves the selected order id by ref.

## 7. Verify

[`verify.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/compiler/verify.py)
checks the compiled behavior before packaging.

Verification has two layers:

- structural validation through `jdsl.ir.validate.validate_ir`
- replay checks for deterministic refs and guards

A compiled ref must resolve in the recorded `state_before` to the exact argument
the episode used. A compiled guard must hold in successful episodes where it
would have allowed the recorded action. Passing replay checks can promote node
provenance from E1/E2 to E4.

Replay verification is not a universal correctness proof. It proves that the
deterministic parts reproduce the source evidence they were compiled from.

## 8. Package Assembly

[`package.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl_harness/compiler/package.py)
turns verified compiled behavior into a `BehaviorPackage`.

The package records:

- `manifest.json`: name, version, runtime, required capabilities, source, verification
- `behavior.json`: restricted Behavior IR
- `tools.json`: logical capability contracts and effect flags
- `signatures/*.json`: residual model interfaces
- `provenance.json`: source episodes, evidence grades, candidate ids
- `tests/*.jsonl`: replay, guard, and signature evidence
- `evidence/summary.json`: candidate and burden summary

Shell-like capabilities default to write/destructive/non-idempotent effects when
no trusted host contract says otherwise.

## Retail Fixture

The compiler tests in
[`test/test_compiler.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/test/test_compiler.py)
show the intended behavior with a fake retail environment.

The teacher behavior is:

```text
lookup(email) -> customer
list_orders(customer_id=customer.id) -> orders
predict(request, orders -> selected_index)
get_order(order_id=orders[$selected_index].id) -> order
```

The tests assert that:

- `customer.id` is discovered as the source of `list_orders.customer_id`
- varying unlinked `email` becomes a runtime input
- invariant unlinked arguments become constants
- repeated tool-call slots stay position-specific
- shell capabilities are treated as potentially mutating by default
- the exported package reloads, verifies digests, binds new host tools, and runs
  with a different small fake model

That fixture is the best executable description of the compiler thesis today.
