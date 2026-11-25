"""P25/P26/P30: Scorer correctness and benchmark determinism (Track C)."""
from __future__ import annotations

from jdsl.ir.schema import BehaviorIR, IRAction, IRSequence
from jdsl_harness.eval.benchmark import run_benchmark, summarise, write_csv
from jdsl_harness.eval.scorer import score_ir
from jdsl_harness.eval.worlds import WorldW0, ground_truth


def _w0_ir(order_ref: str) -> BehaviorIR:
    return BehaviorIR(root=IRSequence(type="sequence", id="flow", children_=[
        IRAction(type="action", id="a0", tool="lookup",
                 arguments={"email": {"ref": "email"}}, store="customer"),
        IRAction(type="action", id="a1", tool="list_orders",
                 arguments={"customer_id": {"ref": "customer.id"}}, store="orders"),
        IRAction(type="action", id="a2", tool="get_order",
                 arguments={"order_id": {"ref": order_ref}}, store="order"),
    ]))


def test_p25_perfect_ir_scores_one():
    gt = ground_truth(WorldW0(seed=1))
    score = score_ir(_w0_ir("orders[$selected_index].id"), gt)
    assert score["ref_precision"] == 1.0
    assert score["ref_recall"] == 1.0
    assert score["spurious_rate"] == 0.0
    assert score["caps_match"] is True


def test_p25_wrong_ir_scores_as_expected():
    gt = ground_truth(WorldW0(seed=1))
    score = score_ir(_w0_ir("orders[99].id"), gt)
    # customer.id recovered (1 tp); orders[99].id spurious (1 fp); planted order
    # ref missing (1 fn).
    assert score["ref_precision"] == 0.5
    assert score["ref_recall"] == 0.5
    assert score["spurious_rate"] == 0.5


def test_p26_benchmark_is_deterministic(tmp_path):
    a = run_benchmark([1, 2], n_episodes=3, worlds=["w0", "w1", "w2"])
    b = run_benchmark([1, 2], n_episodes=3, worlds=["w0", "w1", "w2"])
    assert a == b
    pa = write_csv(a["results"], tmp_path / "a.csv")
    pb = write_csv(b["results"], tmp_path / "b.csv")
    assert pa.read_text() == pb.read_text()


def test_p26_runs_for_multiple_episode_counts():
    for n in (2, 3, 5, 10):
        result = run_benchmark([1], n_episodes=n, worlds=["w0"])
        assert result["count"] == 1
        assert result["results"][0]["compile_ok"] is True


def test_p30_baselines_recover_residual_but_not_guard():
    rows = run_benchmark([1, 2, 3], n_episodes=3,
                         worlds=["w0", "w1", "w2"])["results"]
    summary = summarise(rows)
    # W0/W1 recover the planted dataflow.
    assert summary["w0"]["ref_recall"] == 1.0
    assert summary["w1"]["residual_recovered"] == 1.0
    # Guards are the known gap: the compiler emits no IRGuard yet.
    assert summary["w2"]["guard_recovered"] == 0.0
