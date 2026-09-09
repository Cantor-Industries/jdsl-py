"""Behavior IR: expression language, schema roundtrip, validation, and lowering
into a runnable tree (design §21, §32.1, §35 PR11). The end-to-end shape follows
the retail-cancellation example (§49)."""

from __future__ import annotations

import pytest

from jdsl.context import RunContext
from jdsl.ir import (
    BehaviorIR,
    RuntimeBindings,
    Signature,
    SignatureInput,
    SignatureOutput,
    evaluate,
    lower,
    resolve_path,
    validate_expr,
    validate_ir,
)
from jdsl.ir.schema import (
    IRAction,
    IRGuard,
    IRPredict,
    IRSequence,
    node_from_dict,
    node_to_dict,
)
from jdsl.tree import Status

# -- expression language (§21.2) ----------------------------------------------

def test_resolve_path_dotted_and_indexed():
    bb = {"customer": {"id": "U17"}, "orders": [{"id": "#W1"}, {"id": "#W2"}], "selected_index": 1}
    assert resolve_path("customer.id", bb) == "U17"
    assert resolve_path("orders[0].id", bb) == "#W1"
    assert resolve_path("orders[$selected_index].id", bb) == "#W2"


def test_evaluate_operators():
    bb = {"order": {"status": "pending"}, "confirmation": {"state": "confirmed"}}
    assert evaluate({"in": [{"ref": "order.status"}, ["pending", "processing"]]}, bb)
    assert evaluate({"eq": [{"ref": "confirmation.state"}, "confirmed"]}, bb)
    assert not evaluate({"eq": [{"ref": "confirmation.state"}, "missing"]}, bb)
    assert evaluate({"and": [{"exists": "order"}, {"not": {"exists": "refund"}}]}, bb)


def test_validate_expr_rejects_bad_operator():
    assert validate_expr({"frobnicate": [1, 2]})
    assert not validate_expr({"eq": [{"ref": "a"}, 1]})


# -- schema roundtrip ---------------------------------------------------------

def test_node_roundtrip():
    node = IRSequence(type="sequence", id="flow", children_=[
        IRAction(type="action", id="lookup", tool="retail.customer.lookup", store="customer"),
        IRAction(type="action", id="list", tool="retail.order.list",
                 arguments={"customer_id": {"ref": "customer.id"}}, store="orders"),
        IRGuard(type="guard", id="cancellable",
                expression={"in": [{"ref": "order.status"}, ["pending"]]}),
    ])
    d = node_to_dict(node)
    back = node_from_dict(d)
    assert node_to_dict(back) == d


# -- validation (§32.1) -------------------------------------------------------

def _cancel_ir() -> BehaviorIR:
    sig = Signature(
        id="resolve_target_order", kind="predict",
        inputs={"request": SignatureInput(source="request"),
                "orders": SignatureInput(source="orders", schema={"type": "array"})},
        output=SignatureOutput(name="selected_index", schema={"type": "integer", "minimum": 0}),
        instruction="Choose the order the customer means.",
    )
    root = IRSequence(type="sequence", id="cancel_flow", children_=[
        IRAction(type="action", id="list_orders", tool="retail.order.list",
                 arguments={"customer_id": {"ref": "customer.id"}}, store="orders"),
        IRPredict(type="predict", id="resolve_target", signature="resolve_target_order"),
        IRAction(type="action", id="get_order", tool="retail.order.get",
                 arguments={"order_id": {"ref": "orders[$selected_index].id"}}, store="order"),
        IRGuard(type="guard", id="cancellable",
                expression={"in": [{"ref": "order.status"}, ["pending", "processing"]]}),
    ])
    return BehaviorIR(root=root, signatures={sig.id: sig})


def test_validate_ok():
    report = validate_ir(_cancel_ir())
    assert report.ok, report.problems


def test_validate_flags_unknown_signature_and_unbounded_repeat():
    from jdsl.ir.schema import IRRepeat
    ir = _cancel_ir()
    ir.root.children_.append(IRPredict(type="predict", id="x", signature="missing"))
    ir.root.children_.append(IRRepeat(type="repeat", id="loop",
                                      child=IRAction(type="action", tool="t"), max=999999))
    report = validate_ir(ir)
    assert not report.ok
    assert any("missing" in p for p in report.problems)
    assert any("unbounded" in p for p in report.problems)


def test_validate_required_capabilities():
    ir = _cancel_ir()
    report = validate_ir(ir, required_capabilities={"retail.order.list"})  # get missing
    assert any("retail.order.get" in p for p in report.problems)


# -- lowering + execution (§35 PR11) ------------------------------------------

def test_lower_and_run(fake_model):
    ir = _cancel_ir()
    orders = [{"id": "#W1", "status": "shipped"}, {"id": "#W2", "status": "pending"}]

    def list_orders(customer_id: str):
        return orders

    def get_order(order_id: str):
        return next(o for o in orders if o["id"] == order_id)

    bindings = RuntimeBindings(tools={
        "retail.order.list": list_orders,
        "retail.order.get": get_order,
    })
    tree = lower(ir, bindings)
    # model picks index 1 (the pending order); typed output coerces "1" -> 1
    ctx = RunContext(blackboard={"customer": {"id": "U17"}, "request": "cancel my order"},
                     model=fake_model("1"))
    assert tree.tick(ctx) is Status.SUCCESS
    assert ctx.blackboard["selected_index"] == 1
    assert ctx.blackboard["order"]["id"] == "#W2"


def test_missing_capability_fails_before_run():
    from jdsl.ir import BindingError
    with pytest.raises(BindingError):
        lower(_cancel_ir(), RuntimeBindings(tools={}))  # no tools bound
