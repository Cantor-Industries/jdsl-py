"""P23: Minimal world generator W0 — linear chain, ground truth (Track C).

A seeded synthetic environment (lookup -> list_orders -> get_order) with planted
dataflow structure and uniform target position. Track C options add coincidence
traps (P27), a residual decision over a candidate list (P28), and a policy guard
(P29); each option is reflected in `ground_truth` so the scorer can tell a real
dataflow reference from a coincidence.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Any

from jdsl import act, predict, ref, root, seq, store
from jdsl.trace import EventKind, ListTraceSink, TraceEvent, segment_episodes
from test.conftest import FakeModel


@dataclass
class WorldW0:
    """Tiny retail-style world with deterministic structure."""
    seed: int
    customer_id: str = field(init=False)
    orders: list[dict] = field(init=False)
    target_index: int = field(init=False)  # uniform over valid positions
    trap_value: str = field(init=False)    # P27: unrelated value equal to a real one
    # Track C option flags (P27–P29)
    coincidence_trap: bool = False  # P27
    residual_decision: bool = False  # P28
    policy_guard: bool = False       # P29

    def __post_init__(self) -> None:
        rng = random.Random(self.seed)
        self.customer_id = f"U{self.seed:03d}"
        # Planted: 2 orders; target position uniform over 0,1
        self.target_index = rng.randint(0, 1)
        self.orders = [
            {"id": f"#W{self.seed}0", "status": "pending"},
            {"id": f"#W{self.seed}1", "status": "shipped"},
        ]
        # P27: this value coincides with the customer id but is *not* derived
        # from the lookup result. A compiler that emits a ref for it is wrong.
        self.trap_value = self.customer_id

    # -- tools ----------------------------------------------------------------
    def lookup(self, email: str) -> dict:
        return {"id": self.customer_id, "email": email}

    def list_orders(self, customer_id: str) -> list[dict]:
        assert customer_id == self.customer_id
        return self.orders

    def get_order(self, order_id: str) -> dict:
        return next(o for o in self.orders if o["id"] == order_id)

    def notify(self, reference: str) -> dict:
        """P27: takes a literal reference that happens to equal the customer id."""
        return {"notified": reference}

    def cancel_order(self, order_id: str, status: str) -> dict:
        """P29: the action is only permitted while the order is pending."""
        if status != "pending":
            return {"refused": True, "reason": f"order status {status}"}
        return {"cancelled": True, "order_id": order_id}


def residual_choice(world: WorldW0, episode_index: int = 0) -> int:
    """P28: request-dependent choice that varies across seeds and episodes."""
    return (world.seed + episode_index) % len(world.orders)


def _verdict(sink: ListTraceSink, capture_id: str, episode_id: str,
             verdict: str = "success") -> None:
    sink.events.append(TraceEvent.new(
        kind=EventKind.ENVIRONMENT_VERDICT, actor="environment",
        capture_id=capture_id, episode_id=episode_id, payload={"verdict": verdict}))


def _generate_chain(world: WorldW0, n: int, capture_id: str) -> list:
    """Oracle teacher for the linear chain, honouring the trap/residual flags."""
    sink = ListTraceSink()
    for i in range(n):
        env = world
        # W1 varies the selected index with the request; W0 uses the planted one.
        idx = residual_choice(world, i) if world.residual_decision else world.target_index
        steps = [
            store(act(env.lookup, email=ref("email")), "customer"),
            store(act(env.list_orders, customer_id=ref("customer.id")), "orders"),
            predict("request, orders -> selected_index", id="resolve_target"),
            store(act(env.get_order, order_id=ref(f"orders[{idx}].id")), "order"),
        ]
        if world.coincidence_trap:
            # P27: a literal that coincides with customer.id but is unrelated.
            steps.append(store(act(env.notify, reference=world.trap_value), "notification"))
        root("w0").do(seq(*steps)).run(
            trace_sink=sink, model=FakeModel(str(idx)),
            episode_id=f"ep_{i}", capture_id=capture_id,
            email=f"c{i}@x.com", customer_id=env.customer_id,
            request=f"cancel order {idx}", status="pending")
        _verdict(sink, capture_id, f"ep_{i}")
    return segment_episodes(sink.events)


def _generate_guard(world: WorldW0, n: int, capture_id: str) -> list:
    """P29: alternate allowed (pending) and refused (shipped) episodes."""
    sink = ListTraceSink()
    for i in range(n):
        env = world
        status = "pending" if i % 2 == 0 else "shipped"
        idx = world.target_index
        steps = [
            store(act(env.lookup, email=ref("email")), "customer"),
            store(act(env.list_orders, customer_id=ref("customer.id")), "orders"),
            store(act(env.get_order, order_id=ref(f"orders[{idx}].id")), "order"),
        ]
        if status == "pending":
            # The oracle only acts when the policy predicate holds.
            steps.append(store(
                act(env.cancel_order, order_id=ref("order.id"), status=ref("status")),
                "cancellation"))
        root("w0").do(seq(*steps)).run(
            trace_sink=sink, model=FakeModel("0"),
            episode_id=f"ep_{i}", capture_id=capture_id,
            email=f"c{i}@x.com", customer_id=env.customer_id,
            request="cancel my order", status=status)
        # A refusal that honours the policy is still a successful episode.
        _verdict(sink, capture_id, f"ep_{i}", "success")
    return segment_episodes(sink.events)


def generate_episodes(world: WorldW0, n: int = 3, capture_id: str = "w0") -> list:
    """Run the scripted oracle teacher over the world; return normalized episodes.

    Dispatches on the world options so `WorldW1` / `WorldW2` and the bare flags
    produce the generator they name (P27–P29)."""
    if getattr(world, "policy_guard", False):
        return _generate_guard(world, n, capture_id)
    return _generate_chain(world, n, capture_id)


def ground_truth(world: WorldW0) -> dict[str, Any]:
    """Expected refs, inputs, capabilities and planted traps for the world."""
    gt: dict[str, Any] = {
        "refs": ["customer.id", "orders[$selected_index].id"],
        "inputs": ["email", "request"],
        "capabilities": ["lookup", "list_orders", "get_order"],
        "target_index_range": (0, len(world.orders) - 1),
        "traps": [],
    }
    if world.coincidence_trap:
        gt["capabilities"] = [*gt["capabilities"], "notify"]
        # P27: explicitly labelled "not a ref" so the scorer counts a compiled
        # reference into this slot as spurious.
        gt["traps"] = [{
            "tool": "notify", "arg": "reference", "value": world.trap_value,
            "note": "not a ref",
        }]
    if world.residual_decision:
        gt["residual"] = {
            "signature": "resolve_target",
            "deciding_feature": "request",
            "candidate_list": "orders",
            "choice_ref": "$selected_index",
        }
    if world.policy_guard:
        gt["capabilities"] = [*gt["capabilities"], "cancel_order"]
        gt["inputs"] = ["email", "request", "status"]
        gt["refs"] = ["customer.id", f"orders[{world.target_index}].id",
                      "order.id", "order.status"]
        gt["guard"] = {
            "predicate": "status == 'pending'",
            "allowed_tool": "cancel_order",
            "status_ref": "status",
        }
    return gt


def generate_with_trap(world: WorldW0, n: int = 3, capture_id: str = "w0_trap") -> list:
    """P27: episodes with a coincident unrelated constant (trap)."""
    return _generate_chain(replace(world, coincidence_trap=True), n, capture_id)


def generate_with_residual(world: WorldW0, n: int = 3, capture_id: str = "w0_res") -> list:
    """P28: episodes with a residual decision (variable choice)."""
    return _generate_chain(replace(world, residual_decision=True), n, capture_id)


def generate_with_guard(world: WorldW0, n: int = 3, capture_id: str = "w0_guard") -> list:
    """P29: episodes where the action is allowed only under a planted predicate."""
    return _generate_guard(replace(world, policy_guard=True), n, capture_id)


class WorldW1(WorldW0):
    """P28: Residual decision world (variable choice)."""
    def __post_init__(self) -> None:
        super().__post_init__()
        self.residual_decision = True


class WorldW2(WorldW0):
    """P29: Policy guard world (only when status pending)."""
    def __post_init__(self) -> None:
        super().__post_init__()
        self.policy_guard = True


__all__ = [
    "WorldW0", "WorldW1", "WorldW2", "generate_episodes", "generate_with_trap",
    "generate_with_residual", "generate_with_guard", "ground_truth",
    "residual_choice",
]
