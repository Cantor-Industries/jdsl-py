"""P24: Oracle teacher and outcome checker for W0 (Track C).

The teacher follows the planted policy and emits canonical traces; the checker
verifies the final blackboard state — and, for the guard world (P29), that the
action was not taken when the policy predicate did not hold.
"""
from __future__ import annotations

from typing import Any

from jdsl import act, ref, root, seq, store
from jdsl.trace import EventKind, ListTraceSink, TraceEvent
from jdsl_harness.eval.worlds import WorldW0, ground_truth
from test.conftest import FakeModel


class OracleTeacherW0:
    """Scripted teacher following the planted policy; emits canonical traces."""

    def __init__(self, world: WorldW0):
        self.world = world
        self.ground = ground_truth(world)

    def run_trace(self, sink: ListTraceSink, episode_id: str = "ep_0",
                  capture_id: str = "cap_oracle") -> None:
        env = self.world
        idx = env.target_index
        steps = [
            store(act(env.lookup, email=ref("email")), "customer"),
            store(act(env.list_orders, customer_id=ref("customer.id")), "orders"),
            store(act(env.get_order, order_id=ref(f"orders[{idx}].id")), "order"),
        ]
        if env.policy_guard:
            steps.append(store(
                act(env.cancel_order, order_id=ref("order.id"), status=ref("status")),
                "cancellation"))
        root("w0").do(seq(*steps)).run(
            trace_sink=sink, model=FakeModel("0"), episode_id=episode_id,
            capture_id=capture_id, email="oracle@x.com",
            customer_id=env.customer_id, request="cancel my order", status="pending")
        sink.events.append(TraceEvent.new(
            kind=EventKind.ENVIRONMENT_VERDICT, actor="environment",
            capture_id=capture_id, episode_id=episode_id,
            payload={"verdict": "success"}))


class OutcomeCheckerW0:
    """Verifies final blackboard state matches ground truth / planted policy."""

    def __init__(self, world: WorldW0):
        self.world = world
        self.ground = ground_truth(world)

    def check(self, blackboard: dict[str, Any]) -> bool:
        if self.world.policy_guard:
            cancellation = blackboard.get("cancellation")
            took_action = bool(isinstance(cancellation, dict) and cancellation.get("cancelled"))
            if took_action and blackboard.get("status") != "pending":
                return False  # P29: policy violation
            return True
        # After a correct run: order.id should match the planted target.
        expected_id = self.world.orders[self.world.target_index]["id"]
        actual = blackboard.get("order")
        return bool(actual is not None and actual.get("id") == expected_id)


__all__ = ["OracleTeacherW0", "OutcomeCheckerW0"]
