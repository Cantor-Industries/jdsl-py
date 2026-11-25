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
    return segment_episodes(sink.events)


def ground_truth(world: WorldW0) -> dict[str, Any]:
    """Expected refs, inputs, required capabilities for the world."""
    return {
        "refs": ["customer.id", "orders[$selected_index].id"],
        "inputs": ["email", "request"],
        "capabilities": ["lookup", "list_orders", "get_order"],
        "target_index_range": (0, len(world.orders) - 1),
    }
