"""End-to-end compiler pipeline (design §46 end-to-end fixture, §48 MVP).

A tiny fake retail environment produces frontier-style traces; the compiler mines
exact dataflow, fixed sequence, and the residual semantic decision, verifies by
replay, and exports a .jdslpkg that a *different* frozen small model runs.
"""

from __future__ import annotations

from jdsl import act, predict, ref, root, seq, store
from jdsl.context import RunContext
from jdsl.package import export_jdslpkg, load_package
from jdsl.trace import ListTraceSink, segment_episodes
from jdsl.tree import Status
from jdsl_harness.compiler import (
    compile_behavior,
    consolidate,
    find_source,
    normalize_all,
)
from jdsl_harness.compiler.lineage import is_meaningful

# -- fake retail environment (§46) --------------------------------------------

class Retail:
    """Deterministic fake environment. Different customers/orders per episode so
    dataflow lineage is real, not coincidental."""

    def __init__(self, customer_id: str, orders: list[dict]) -> None:
        self.customer_id = customer_id
        self.orders = orders

    def lookup(self, email: str) -> dict:
        return {"id": self.customer_id, "email": email}

    def list_orders(self, customer_id: str) -> list[dict]:
        assert customer_id == self.customer_id
        return self.orders

    def get_order(self, order_id: str) -> dict:
        return next(o for o in self.orders if o["id"] == order_id)


def _teacher_skill(env: Retail):
    """The 'frontier' behavior: lookup -> list -> (choose) -> get. The teacher
    always copies the exact ids; the compiler should turn those into refs."""
    return root("cancel").do(seq(
        store(act(env.lookup, email=ref("email")), "customer"),
        store(act(env.list_orders, customer_id=ref("customer_id")), "orders"),
        predict("request, orders -> selected_index", id="resolve_target"),
        store(act(env.get_order, order_id=ref("target_order_id")), "order"),
    ))


def _capture(n: int) -> list:
    """Run the teacher n times over different data, capturing canonical traces."""
    sink = ListTraceSink()
    for i in range(n):
        cid = f"U{i}"
        orders = [{"id": f"#W{i}0", "status": "shipped"}, {"id": f"#W{i}1", "status": "pending"}]
        env = Retail(cid, orders)
        # the teacher picks the pending order (index 1); its exact id is seeded as
        # the get_order arg so lineage links orders[1].id -> get_order.order_id
        from test.conftest import FakeModel
        model = FakeModel("1")
        _teacher_skill(env).run(
            trace_sink=sink, model=model, episode_id=f"ep_{i}", capture_id="cap_test",
            email=f"c{i}@x.com", customer_id=cid, target_order_id=f"#W{i}1", request="cancel my order",
        )
    return segment_episodes(sink.events)


# -- unit: lineage on real captures -------------------------------------------

def test_lineage_finds_customer_id_flow():
    episodes = _capture(1)
    norm = normalize_all(episodes)
    # list_orders.customer_id should be sourced from customer.id
    steps = {s.logical_tool: s for s in norm[0].steps}
    assert steps["list_orders"].arg_lineage["customer_id"] == "customer.id"


def test_is_meaningful_filters_trivia():
    assert is_meaningful("#W01")
    assert not is_meaningful(1)
    assert not is_meaningful(True)
    assert find_source("x", {"a": "x"}) is None  # single char, too trivial


# -- consolidation grades -----------------------------------------------------

def test_dataflow_candidate_is_graded():
    norm = normalize_all(_capture(4))
    cands = consolidate(norm)
    flows = [c for c in cands if c.type == "DATAFLOW"
             and c.claim["target"]["tool"] == "list_orders"]
    assert flows and flows[0].evidence.support == 4
    assert flows[0].evidence.counterexamples == 0
    assert flows[0].grade in ("E2", "E3", "E4")


# -- full pipeline ------------------------------------------------------------

def test_compile_verify_export_run(tmp_path):
    episodes = _capture(5)
    result = compile_behavior(episodes, name="retail-cancellation", task_family="retail-support")

    # structure + verification
    assert result.verification.structural_ok, result.verification.to_dict()
    assert result.verification.replay_coverage == 1.0
    assert result.verification.ok

    # burden: the model only makes the one semantic decision
    stats = result.compiled.stats
    assert stats["model_dependent_decisions"] == 1
    assert stats["residual_decision_burden"] < 0.5
    assert stats["exact_dataflow_refs"] >= 2  # customer.id + order id flows

    # the compiled IR replaced exact id copying with refs
    from jdsl.ir.schema import IRAction
    actions = {n.tool: n for n in result.compiled.ir.walk() if isinstance(n, IRAction)}
    assert "ref" in actions["list_orders"].arguments["customer_id"]
    assert actions["list_orders"].arguments["customer_id"]["ref"] == "customer.id"

    # export -> reload (fresh, structural + digest verification) -> run
    path = export_jdslpkg(result.package, tmp_path / "retail")
    loaded = load_package(path)
    assert loaded.manifest.required_capabilities

    # a *frozen small model* runs the package on unseen data
    env = Retail("U99", [{"id": "#W990", "status": "shipped"}, {"id": "#W991", "status": "pending"}])
    tools = {"lookup": env.lookup, "list_orders": env.list_orders, "get_order": env.get_order}
    from test.conftest import FakeModel
    small = FakeModel("1")  # chooses the pending order
    bound = loaded.as_root(tools)
    ctx = RunContext(blackboard={"customer": {"id": "U99"}, "request": "cancel"}, model=small)
    # seed the lookup output the compiled tree expects
    assert bound.tick(ctx) is Status.SUCCESS
    assert ctx.blackboard["order"]["id"] == "#W991"


def test_second_small_model_runs_same_package(tmp_path):
    """Portability (§34.3): the same package runs with a different small model."""
    result = compile_behavior(_capture(4), name="retail-cancellation")
    loaded = load_package(export_jdslpkg(result.package, tmp_path / "r"))
    env = Retail("U7", [{"id": "#W70", "status": "pending"}, {"id": "#W71", "status": "shipped"}])
    tools = {"lookup": env.lookup, "list_orders": env.list_orders, "get_order": env.get_order}
    from test.conftest import FakeModel
    other = FakeModel("0")  # a different model family choosing index 0
    ctx = RunContext(blackboard={"customer": {"id": "U7"}, "request": "cancel"}, model=other)
    assert loaded.as_root(tools).tick(ctx) is Status.SUCCESS
    assert ctx.blackboard["order"]["id"] == "#W70"
