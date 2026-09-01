"""Behavior package: export to dir/.jdsl, deterministic bytes, digest
verification, structural loader rules, bind + run (design §22, §40, §45)."""

from __future__ import annotations

import zipfile

import pytest

from jdsl.context import RunContext
from jdsl.ir.schema import (
    BehaviorIR,
    IRAction,
    IRGuard,
    IRPredict,
    IRSequence,
    Signature,
    SignatureInput,
    SignatureOutput,
)
from jdsl.package import (
    BehaviorPackage,
    Manifest,
    PackageError,
    ToolContract,
    ToolEffects,
    export_dir,
    export_jdsl,
    load_package,
    package_digest,
)
from jdsl.package.manifest import NodeProvenance
from jdsl.tree import Status


def _pkg() -> BehaviorPackage:
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
    ir = BehaviorIR(root=root, signatures={sig.id: sig})
    manifest = Manifest(
        name="retail-cancellation", version="0.1.0", task_family="retail-support",
        required_capabilities=["retail.order.list", "retail.order.get"],
        source={"capture_fidelity": "F3", "episode_count": 3},
        verification={"status": "passed", "replay_coverage": 1.0},
    )
    tools = [
        ToolContract("retail.order.list", effects=ToolEffects(read_only=True)),
        ToolContract("retail.order.get", effects=ToolEffects(read_only=True)),
    ]
    prov = [NodeProvenance(node_id="cancellable", evidence_grade="E3",
                           rationale_summary="policy: only pending/processing cancellable")]
    return BehaviorPackage(manifest=manifest, ir=ir, tools=tools, provenance=prov,
                           tests={"replay": [{"episode": "ep_1", "ok": True}]})


def test_export_dir_and_load_and_run(tmp_path, fake_model):
    export_dir(_pkg(), tmp_path / "pkg")
    loaded = load_package(tmp_path / "pkg")
    assert loaded.name == "retail-cancellation"
    assert loaded.permissions() == {"reads": ["retail.order.get", "retail.order.list"], "writes": []}

    orders = [{"id": "#W1", "status": "shipped"}, {"id": "#W2", "status": "pending"}]
    tools = {"retail.order.list": lambda customer_id: orders,
             "retail.order.get": lambda order_id: next(o for o in orders if o["id"] == order_id)}
    root = loaded.as_root(tools)
    ctx = RunContext(blackboard={"customer": {"id": "U17"}, "request": "cancel"}, model=fake_model("1"))
    assert root.tick(ctx) is Status.SUCCESS
    assert ctx.blackboard["order"]["id"] == "#W2"


def test_jdsl_is_deterministic(tmp_path):
    a = export_jdsl(_pkg(), tmp_path / "a")
    b = export_jdsl(_pkg(), tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()
    assert package_digest(_pkg()) == package_digest(_pkg())
    assert zipfile.is_zipfile(a)


def test_jdsl_roundtrip(tmp_path, fake_model):
    path = export_jdsl(_pkg(), tmp_path / "retail")
    loaded = load_package(path)
    assert loaded.manifest.verification["status"] == "passed"
    root = loaded.as_root({"retail.order.list": lambda customer_id: [{"id": "#W2", "status": "pending"}],
                           "retail.order.get": lambda order_id: {"id": "#W2", "status": "pending"}})
    ctx = RunContext(blackboard={"customer": {"id": "U17"}, "request": "cancel"}, model=fake_model("0"))
    assert root.tick(ctx) is Status.SUCCESS


def test_digest_tamper_rejected(tmp_path):
    root = export_dir(_pkg(), tmp_path / "pkg")
    behavior = root / "behavior.json"
    behavior.write_text(behavior.read_text().replace("retail.order.list", "retail.order.evil"))
    with pytest.raises(PackageError, match="digest mismatch"):
        load_package(root)


def test_missing_capability_binding_rejected(tmp_path):
    loaded = load_package(export_dir(_pkg(), tmp_path / "pkg"))
    with pytest.raises(PackageError, match="not bound"):
        loaded.bind({"retail.order.list": lambda customer_id: []})  # get missing


def test_unsupported_format_rejected(tmp_path):
    pkg = _pkg()
    pkg.manifest.format = "jdsl.package.v999"
    with pytest.raises(PackageError, match="unsupported package format"):
        load_package(export_dir(pkg, tmp_path / "pkg"))
