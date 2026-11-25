"""P23: Minimal world generator W0 — linear chain, ground truth (Track C).

A seeded synthetic environment (lookup -> list_orders -> get_order) with planted
dataflow structure and uniform target position.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from jdsl import act, predict, ref, root, seq, store
from jdsl.trace import ListTraceSink, segment_episodes
from test.conftest import FakeModel


@dataclass
class WorldW0:
    """Tiny retail-style world with deterministic structure."""
    seed: int
    customer_id: str = field(init=False)
    orders: list[dict] = field(init=False)
    target_index: int = field(init=False)  # uniform over valid positions
    # Track C option flags (P27–P29)
    coincidence_trap: bool = False  # P27
    residual_decision: bool = False  # P28
    policy_guard: bool = False  # P29

    def __post_init__(self) -> None:
        rng = random.Random(self.seed)
        self.customer_id = f"U{self.seed:03d}"
        # Planted: 2 orders; target position uniform over 0,1
        self.target_index = rng.randint(0, 1)
        self.orders = [
            {"id": f"#W{self.seed}0", "status": "pending"},
            {"id": f"#W{self.seed}1", "status": "shipped"},
        ]

    def lookup(self, email: str) -> dict:
        return {"id": self.customer_id, "email": email}

    def list_orders(self, customer_id: str) -> list[dict]:
        assert customer_id == self.customer_id
        return self.orders

    def get_order(self, order_id: str) -> dict:
        return next(o for o in self.orders if o["id"] == order_id)


def generate_episodes(world: WorldW0, n: int = 3, capture_id: str = "w0") -> list:
    """Run scripted oracle teacher over world; return normalized episodes."""
    from jdsl_harness.compiler.normalize import normalize_all
    sink = ListTraceSink()
    for i in range(n):
        # Uniform selection over positions (planted decision)
        idx = (world.seed + i) % len(world.orders)
        env = world
        skill = root("w0").do(seq(
            store(act(env.lookup, email=ref("email")), "customer"),
            store(act(env.list_orders, customer_id=ref("customer.id")), "orders"),
            predict("request, orders -> selected_index", id="resolve_target"),
            store(act(env.get_order, order_id=ref(f"orders[{idx}].id")), "order"),
        ))
        # Fixed small model picks the same index every time for this seed
        skill.run(
            trace_sink=sink, model=FakeModel(str(idx)),
            episode_id=f"ep_{i}", capture_id=capture_id,
            email=f"c{i}@x.com", customer_id=env.customer_id,
            request="cancel my order",
        )
    from jdsl.trace import segment_episodes
    # P15: episodes need explicit success for skeleton selection
    from jdsl.trace import TraceEvent, EventKind
    for i in range(n):
        sink.events.append(TraceEvent.new(
            kind=EventKind.ENVIRONMENT_VERDICT, actor="environment", capture_id=capture_id,
            episode_id=f"ep_{i}", payload={"verdict": "success"}))
    return segment_episodes(sink.events)


def ground_truth(world: WorldW0) -> dict[str, Any]:
    """Expected refs, inputs, required capabilities for the world."""
    return {
        "refs": ["customer.id", "orders[$selected_index].id"],
        "inputs": ["email", "request"],
        "capabilities": ["lookup", "list_orders", "get_order"],
        "target_index_range": (0, len(world.orders) - 1),
    }


def generate_with_trap(world: WorldW0, n: int = 3, capture_id: str = "w0_trap") -> list:
    """P27: episodes with coincident unrelated constant (trap)."""
    # Simplified: same as generate_episodes but injects unrelated equal constant
    from jdsl.trace import ListTraceSink, segment_episodes
    sink = ListTraceSink()
    for i in range(n):
        env = world
        from jdsl import root, seq, store, act, ref
        root("w0").do(seq(
            store(act(env.lookup, email=ref("email")), "customer"),
            store(act(env.list_orders, customer_id=ref("customer.id")), "orders"),
            store(act(env.get_order, order_id=ref(f"orders[{world.target_index}].id")), "order"),
        )).run(trace_sink=sink, model=FakeModel("0"), episode_id=f"ep_{i}", capture_id=capture_id,
                email="t@x.com", customer_id=env.customer_id, request="cancel")
    return segment_episodes(sink.events)

def generate_with_residual(world: WorldW0, n: int = 3, capture_id: str = "w0_res") -> list:
    """P28: episodes with residual decision (variable choice)."""
    from jdsl.trace import ListTraceSink, segment_episodes
    sink = ListTraceSink()
    for i in range(n):
        env = world
        idx = (world.seed + i) % len(env.orders)
        from jdsl import root, seq, store, act, predict, ref
        root("w0").do(seq(
            store(act(env.lookup, email=ref("email")), "customer"),
            store(act(env.list_orders, customer_id=ref("customer.id")), "orders"),
            predict("request, orders -> selected_index", id="resolve"),
            store(act(env.get_order, order_id=ref(f"orders[{idx}].id")), "order"),
        )).run(trace_sink=sink, model=FakeModel(str(idx)), episode_id=f"ep_{i}", capture_id=capture_id,
                email="t@x.com", customer_id=env.customer_id, request="cancel")
    return segment_episodes(sink.events)

def generate_with_guard(world: WorldW0, n: int = 3, capture_id: str = "w0_guard") -> list:
    """P29: episodes where action allowed only when status == pending (guard)."""
    from jdsl.trace import ListTraceSink, segment_episodes
    sink = ListTraceSink()
    for i in range(n):
        env = world
        status = "pending" if i < 2 else "done"
        from jdsl import root, seq, store, act, ref
        root("w0").do(seq(
            store(act(env.lookup, email=ref("email")), "customer"),
            store(act(env.list_orders, customer_id=ref("customer.id")), "orders"),
            store(act(lambda status=status: {"result": status == "pending"}, status=ref("status")), "guarded"),
        )).run(trace_sink=sink, model=FakeModel("0"), episode_id=f"ep_{i}", capture_id=capture_id,
                email="t@x.com", customer_id=env.customer_id, status=status, request="cancel")
    return segment_episodes(sink.events)


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
