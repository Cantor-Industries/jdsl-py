"""Reproduction tests for suspected defects (evaluation plan §2).

Each test targets one suspicion. Expected today: most fail for the stated
reason and are marked xfail(strict=True).  If a test passes, the suspicion
was wrong — delete the xfail and record it as "not reproduced."

No behavior changes here: tests and fixtures only.
"""

from __future__ import annotations

import json

import pytest

from jdsl import act, ref, root, store
from jdsl.context import RunContext
from jdsl.ir.schema import BehaviorIR, IRAction, IRSelector
from jdsl.package import (
    BehaviorPackage,
    Manifest,
    PackageError,
    ToolContract,
    ToolEffects,
    export_dir,
    export_jdsl,
    load_package,
)
from jdsl.trace import ListTraceSink, segment_episodes
from jdsl.tree import Status
from jdsl_harness.compiler import compile_behavior
from test.conftest import FakeModel

# ---------------------------------------------------------------------------
# P02: D8 — positional args dropped in compiled actions
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "D8 [suspected]: _build_action skips _argN keys, so positional arguments "
    "are dropped from compiled actions."
))
def test_d8_positional_args_survive_compilation(tmp_path):
    """A tool called with a positional arg: compile and run; the tool must
    receive the argument."""

    received = {}

    def my_tool(value):
        received["value"] = value
        return {"ok": True}

    # build episodes with a positional arg via act(fn, "x")
    sink = ListTraceSink()
    for i in range(3):
        val = f"item_{i}"
        skill = root("pos").do(store(act(my_tool, val), "result"))
        skill.run(trace_sink=sink, model=FakeModel("0"), episode_id=f"ep_{i}",
                  capture_id="cap_pos")
    episodes = segment_episodes(sink.events)

    result = compile_behavior(episodes, name="pos-test")
    loaded = load_package(export_jdsl(result.package, tmp_path / "pos_test"))

    # run the compiled package — the tool should get a value argument
    received.clear()
    bound = loaded.as_root({"my_tool": my_tool})
    ctx = RunContext(blackboard={}, model=FakeModel("0"))
    status = bound.tick(ctx)
    assert status is Status.SUCCESS
    assert "value" in received, "positional argument was not passed to the tool"


# ---------------------------------------------------------------------------
# P03: D6 — out-of-range residual index escapes instead of falling back
# ---------------------------------------------------------------------------

def test_d6_bad_residual_index_falls_back(tmp_path):
    """A residual model leaf can emit index 99. The compiled selector must treat
    the unresolvable ref as a failed branch and run its fallback, not crash."""

    calls = []

    def get_order(order_id):
        calls.append(("get_order", order_id))
        return {"id": order_id, "status": "pending"}

    def first_order():
        calls.append(("first_order",))
        return {"id": "#W0", "status": "pending"}

    ir = BehaviorIR(root=IRSelector(type="selector", id="recover_selection", children_=[
        IRAction(type="action", id="get_selected_order", tool="retail.order.get",
                 arguments={"order_id": {"ref": "orders[$selected_index].id"}}, store="order"),
        IRAction(type="action", id="fallback_first_order", tool="retail.order.first",
                 arguments={}, store="order"),
    ]))
    manifest = Manifest(name="bad-residual-index", required_capabilities=[
        "retail.order.get", "retail.order.first"])
    pkg = BehaviorPackage(manifest=manifest, ir=ir, tools=[
        ToolContract("retail.order.get", effects=ToolEffects(read_only=True)),
        ToolContract("retail.order.first", effects=ToolEffects(read_only=True)),
    ])
    loaded = load_package(export_jdsl(pkg, tmp_path / "bad_index"))
    bound = loaded.as_root({"retail.order.get": get_order, "retail.order.first": first_order})

    ctx = RunContext(blackboard={
        "orders": [{"id": "#W0", "status": "pending"}, {"id": "#W1", "status": "shipped"}],
        "selected_index": 99,
    })
    status = bound.tick(ctx)  # today: KeyError escapes here

    assert status is Status.SUCCESS
    assert calls == [("first_order",)]  # the bad branch made no tool call
    assert ctx.blackboard["order"]["id"] == "#W0"


def test_d6_authored_ref_missing_still_raises():
    """Compiled actions suppress missing-ref errors; authored act(...) must keep
    raising so authors see mistakes immediately (P13 guard)."""
    with pytest.raises(KeyError, match="not on the blackboard"):
        act(lambda x: x, ref("missing")).tick(RunContext())


# ---------------------------------------------------------------------------
# P04: D9 — unlisted signature file loaded without rejection
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "D9 [suspected]: _load_signatures ignores manifest.files and loads any "
    "signatures/*.json; an unlisted file is not rejected."
))
def test_d9_unlisted_signature_file_rejected(tmp_path):
    """A .jdsl with signatures/evil.json not listed in manifest.files must
    raise PackageError on load (§22.2, D9)."""
    from test.test_package import _pkg

    pkg = _pkg()
    pkg_path = export_dir(pkg, tmp_path / "valid_pkg")
    bad_sig = {
        "format": "jdsl.signature.v1",
        "id": "evil_sig",
        "kind": "predict",
        "inputs": {},
        "output": {"name": "bad", "schema": {"type": "string"}},
        "instruction": "",
    }
    (pkg_path / "signatures" / "evil.json").write_text(json.dumps(bad_sig))
    with pytest.raises(PackageError):
        load_package(pkg_path)
