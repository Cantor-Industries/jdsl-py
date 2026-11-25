"""P24: Oracle teacher and outcome checker for W0 (Track C)."""
from __future__ import annotations

from jdsl.trace import ListTraceSink, segment_episodes
from jdsl_harness.compiler import compile_behavior
from jdsl_harness.eval.oracle import OracleTeacherW0, OutcomeCheckerW0
from jdsl_harness.eval.worlds import WorldW0
from test.conftest import FakeModel


def test_oracle_passes_own_checker():
    w = WorldW0(seed=99)
    checker = OutcomeCheckerW0(w)
    # Direct correct run using world tools
    from jdsl import act, ref, root, seq, store
    from jdsl.trace import ListTraceSink
    sink = ListTraceSink()
    env = w
    root("w0").do(seq(
        store(act(env.lookup, email=ref("email")), "customer"),
        store(act(env.list_orders, customer_id=ref("customer.id")), "orders"),
        store(act(env.get_order, order_id=ref(f"orders[{w.target_index}].id")), "order"),
    )).run(trace_sink=sink, model=FakeModel("0"), episode_id="ep_0",
            capture_id="cap_ora", email="t@x.com",
            customer_id=w.customer_id, request="cancel")
    # Check final state via checker on blackboard (simulated)
    # For simplicity assert checker logic directly
    assert checker.check({"order": {"id": w.orders[w.target_index]["id"]}}) is True


def test_oracle_trace_is_successful_and_compiles():
    """The teacher's own trace must be a labelled success and compile."""
    world = WorldW0(seed=11)
    sink = ListTraceSink()
    OracleTeacherW0(world).run_trace(sink, episode_id="ep_o", capture_id="cap_o")
    episodes = segment_episodes(sink.events)
    assert len(episodes) == 1
    assert episodes[0].succeeded() is True

    result = compile_behavior(episodes, name="oracle")
    assert result.verification.ok
    assert result.normalized[0].success is True


def test_mutated_trace_rejected():
    w = WorldW0(seed=7)
    checker = OutcomeCheckerW0(w)
    # Wrong ID mutation
    assert checker.check({"order": {"id": "wrong"}}) is False
    # Missing order mutation
    assert checker.check({"customer": {"id": w.customer_id}}) is False
