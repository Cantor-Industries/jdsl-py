# Package Runtime

Compiled behavior is not emitted as Python. It is emitted as restricted Behavior
IR plus contracts, signatures, provenance, and tests.

Source map:

| Area | Implementation |
| --- | --- |
| IR schema | [`jdsl/ir/schema.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/ir/schema.py) |
| guard expressions | [`jdsl/ir/expr.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/ir/expr.py) |
| IR validation | [`jdsl/ir/validate.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/ir/validate.py) |
| lowering | [`jdsl/ir/lower.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/ir/lower.py) |
| manifest/contracts | [`jdsl/package/manifest.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/package/manifest.py) |
| export | [`jdsl/package/export.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/package/export.py) |
| load/bind | [`jdsl/package/load.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/package/load.py) |

## Behavior IR

The IR is a JSON form of the behavior tree. It has a fixed node vocabulary:

- `sequence`
- `selector`
- `optional`
- `invert`
- `repeat`
- `action`
- `guard`
- `guard_call`
- `predict`
- `react`

An action node names a logical tool capability:

```json
{
  "type": "action",
  "id": "list_orders_1",
  "tool": "list_orders",
  "arguments": {"customer_id": {"ref": "customer.id"}},
  "store": "orders"
}
```

That logical capability id is the only thing the package knows. The callable is
supplied later by the host. This is why package loading has two phases:

```text
load and verify files
bind logical capabilities to local functions
lower IR to runtime nodes
```

The package never imports host code by path.

## Refs

Lowering turns `{"ref": "customer.id"}` into `Ref("customer.id")`. At runtime,
`Action._resolve` first checks for a direct blackboard key, then falls back to
the path resolver in `jdsl.ir.expr`.

Paths support:

```text
customer.id
orders[0].id
orders[$selected_index].id
```

The dynamic `$selected_index` form is what lets a residual model output choose
an item while deterministic code copies the actual id.

Refs are resolved at runtime by the same mechanism used by handwritten
`act(..., ref(...))` calls. Compiled packages do not need a separate interpreter;
lowering turns IR refs into `Ref` objects and uses the existing `Action` node.

## Guards

`guard` uses a safe JSON expression tree:

```json
{"in": [{"ref": "order.status"}, ["pending", "processing"]]}
```

Supported operators are `exists`, comparisons, `in`, `and`, `or`, and `not`.
There is no embedded Python.

For domain logic that cannot fit the expression language, `guard_call` names a
trusted predicate supplied by the host at bind time.

## Loading

`load_package(path)` accepts an unpacked package directory or `.jdsl` zip.

It verifies:

1. `manifest.json` exists
2. package format is supported
3. file digests match the manifest
4. `behavior.json` exists
5. signatures load
6. IR validates structurally

Only after this does binding happen.

Digest verification is based on `manifest.files`. The manifest records the hash
of every other package file; `load_package` recomputes each digest before parsing
the behavior. The manifest itself is not included in that digest table because
it contains the table.

## Binding

`LoadedPackage.bind(tools, predicates)` requires every manifest capability to be
present in `tools`.

```python
tools = {
    "lookup": lookup,
    "list_orders": list_orders,
    "get_order": get_order,
}

root = load_package("retail.jdsl").as_root(tools, model_id="deepseek-chat")
ctx = root.run(email="ada@example.com", request="cancel my order")
```

Missing capabilities fail before execution. Package code never imports host
tools by itself.

`LoadedPackage.permissions()` splits declared tool contracts into read and write
sets using effect flags. Hosts can show those permissions before deciding whether
to bind a package.

## Deterministic Archives

`export_jdsl` writes a zip with sorted entries and fixed ZIP timestamps. The same
package contents produce the same bytes and digest. That makes later signing and
review straightforward.

`export_dir` writes the same logical package as an unpacked directory for local
development. `.jdsl` is the transport format; the directory form is easier to
inspect in a worktree.
