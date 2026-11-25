"""P27-P29: World generator options (coincidence trap / residual / guard).

Each test exercises the option through the public generator and the scorer, not
just the presence of a flag.
"""
from __future__ import annotations

import json

from jdsl.ir.schema import BehaviorIR, IRAction, IRPredict, IRSequence
from jdsl_harness.compiler import compile_behavior
from jdsl_harness.eval.oracle import OutcomeCheckerW0
from jdsl_harness.eval.scorer import score_ir
from jdsl_harness.eval.worlds import (
    WorldW0,
    WorldW1,
    WorldW2,
    generate_episodes,
    ground_truth,
    residual_choice,
)


def _tool_names(episode) -> set[str]:
    return {
        e.payload.get("tool", {}).get("host_name")
        for e in episode.ordered()
        if e.kind == "tool.call.started"
    }


# ---------------------------------------------------------------------------
# P27: coincidence trap
# ---------------------------------------------------------------------------
def test_p27_trap_is_present_in_traces_and_labelled():
    world = WorldW0(seed=7, coincidence_trap=True)
    episodes = generate_episodes(world, n=2, capture_id="trap")

    traps = ground_truth(world)["traps"]
    assert traps == [{
        "tool": "notify", "arg": "reference",
        "value": world.trap_value, "note": "not a ref",
    }]
    # The coincident value really appears in the recorded traces.
    payloads = json.dumps([e.payload for ep in episodes for e in ep.ordered()],
                          default=str)
    assert world.trap_value in payloads


def test_p27_scorer_counts_a_ref_to_a_trap_as_spurious():
    world = WorldW0(seed=7, coincidence_trap=True)
    ir = BehaviorIR(root=IRSequence(type="sequence", id="flow", children_=[
        IRAction(type="action", id="a0", tool="lookup",
                 arguments={"email": {"ref": "email"}}, store="customer"),
        IRAction(type="action", id="a1", tool="list_orders",
                 arguments={"customer_id": {"ref": "customer.id"}}, store="orders"),
        IRAction(type="action", id="a2", tool="get_order",
                 arguments={"order_id": {"ref": "orders[$selected_index].id"}},
                 store="order"),
        # A compiled ref into the trap slot: value matches, provenance is fake.
        IRAction(type="action", id="a3", tool="notify",
                 arguments={"reference": {"ref": "customer.id"}},
                 store="notification"),
    ]))
    score = score_ir(ir, ground_truth(world))
    assert score["ref_precision"] == 2 / 3
    assert score["spurious_rate"] > 0


# ---------------------------------------------------------------------------
# P28: residual decision (W1)
# ---------------------------------------------------------------------------
def test_p28_choice_varies_across_seeds_and_compiles():
    choices = {residual_choice(WorldW1(seed=s)) for s in range(10)}
    assert choices == {0, 1}, "residual choice should vary across seeds"

    world = WorldW1(seed=99)
    gt = ground_truth(world)
    assert gt["residual"]["deciding_feature"] == "request"

    result = compile_behavior(generate_episodes(world, n=3, capture_id="res"),
                              name="w1_res")
    assert result.verification.ok
    assert any(isinstance(n, IRPredict) for n in result.compiled.ir.walk())


# ---------------------------------------------------------------------------
# P29: policy guard (W2)
# ---------------------------------------------------------------------------
def test_p29_guard_generates_action_and_refusal_episodes():
    world = WorldW2(seed=7)
    episodes = generate_episodes(world, n=3, capture_id="guard")
    acted = ["cancel_order" in _tool_names(ep) for ep in episodes]
    assert any(acted), "the allowed episode should call the guarded action"
    assert not all(acted), "the refused episode should not call the guarded action"
    assert ground_truth(world)["guard"]["predicate"] == "status == 'pending'"


def test_p29_checker_rejects_policy_violation():
    checker = OutcomeCheckerW0(WorldW2(seed=7))
    # Taking the action while pending is allowed.
    assert checker.check({"cancellation": {"cancelled": True}, "status": "pending"})
    # Taking it while not pending is a violation.
    assert not checker.check({"cancellation": {"cancelled": True}, "status": "shipped"})


def test_p29_guard_world_compiles():
    result = compile_behavior(generate_episodes(WorldW2(seed=7), n=3,
                                                capture_id="guard"),
                              name="w2_guard")
    assert result.verification.ok
    tools = {n.tool for n in result.compiled.ir.walk() if isinstance(n, IRAction)}
    assert "cancel_order" in tools
