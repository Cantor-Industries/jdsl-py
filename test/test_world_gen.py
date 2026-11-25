"""P23: Minimal world generator W0 (Track C)."""
from __future__ import annotations

from jdsl_harness.eval.worlds import WorldW0, generate_episodes, ground_truth


def test_world_seed_reproducibility():
    w1 = WorldW0(seed=42)
    w2 = WorldW0(seed=42)
    assert w1.customer_id == w2.customer_id
    assert w1.orders == w2.orders
    assert w1.target_index == w2.target_index


def test_world_target_uniform():
    """Target index should vary over seeds, not always constant."""
    positions = {WorldW0(seed=s).target_index for s in range(20)}
    assert len(positions) > 1, "target index should vary across seeds"


def test_episodes_contain_planted_refs():
    w = WorldW0(seed=7)
    eps = generate_episodes(w, n=2, capture_id="w0_test")
    assert len(eps) == 2
    # First episode should contain tool calls with the planted service names
    events = eps[0].ordered()
    tool_names = {e.payload.get("tool", {}).get("host_name") for e in events if e.kind == "tool.call.started"}
    assert "lookup" in tool_names or "list_orders" in tool_names
