# Behavior Packages

A `.jdsl` file is a deterministic zip archive containing executable policy,
contracts, provenance, and replay evidence. It does not contain Python tool
implementations.

## Package Contents

| File | Role |
| --- | --- |
| `manifest.json` | Package name, format, required capabilities, verification, file digests. |
| `behavior.json` | Behavior IR tree. |
| `tools.json` | Logical capability contracts and effect flags. |
| `signatures/*.json` | Residual model signatures. |
| `provenance.json` | Evidence and rationale for compiled nodes. |
| `tests/*.jsonl` | Replay, signature, or guard evidence when present. |

`load_package` verifies the format, file digests, and IR structure before any
tool is bound.

## Binding Tools

The host provides trusted callables by logical capability id:

```python
TOOLS = {
    "lookup": lookup_customer,
    "list_orders": list_orders,
    "get_order": get_order,
}
```

Then run:

```bash
uv run jdsl package inspect retail.jdsl
uv run jdsl package verify retail.jdsl
uv run jdsl package run retail.jdsl --tools examples/harness/retail_tools.py \
  -i email=ada@example.com -i request="cancel my order"
```

If a required capability is missing, binding fails before execution.

## Refs and Residual Decisions

Compiled actions use argument specs:

```json
{"customer_id": {"ref": "customer.id"}}
{"order_id": {"ref": "orders[$selected_index].id"}}
{"region": {"const": "us-east"}}
```

The first is exact dataflow. The second combines exact dataflow with a residual
model decision: the small model writes `selected_index`, and deterministic path
resolution extracts the matching order id. The third is an invariant constant
observed across episodes.

## Safety Boundaries

Packages can express only the restricted Behavior IR:

- bounded tree nodes
- action calls to named host capabilities
- safe JSON guard expressions
- residual `predict` or `react` signatures

They cannot ship arbitrary Python code. Host tools and guard predicates are
bound explicitly by the runtime.
