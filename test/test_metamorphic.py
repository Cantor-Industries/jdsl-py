"""P32: Metamorphic compile tests (Track C).

These check invariants of the compiler that must hold regardless of incidental
properties of the input, using the W0 world generator as the fixture:

* permuting episode order gives an identical package digest;
* renaming entity ids gives a structurally identical IR (values are abstracted
  into refs, so the concrete ids never leak into the compiled behavior);
* duplicating episodes changes support only, not the compiled structure.
"""
from __future__ import annotations

from jdsl.package.export import package_digest
from jdsl_harness.compiler import compile_behavior
from jdsl_harness.eval.worlds import WorldW0, generate_episodes


def test_permuting_episode_order_preserves_digest():
    episodes = generate_episodes(WorldW0(seed=42), n=3, capture_id="meta")
    forward = compile_behavior(episodes, name="meta")
    reversed_ = compile_behavior(list(reversed(episodes)), name="meta")
    assert forward.compiled.ir.to_dict() == reversed_.compiled.ir.to_dict()
    assert package_digest(forward.package) == package_digest(reversed_.package)


def test_renaming_entity_ids_preserves_ir():
    class RenamedWorld(WorldW0):
        def __post_init__(self) -> None:
            super().__post_init__()
            self.customer_id = "RENAMED-" + self.customer_id
            self.orders = [{"id": "RENAMED-" + o["id"], "status": o["status"]}
                           for o in self.orders]
            self.trap_value = self.customer_id

    base = generate_episodes(WorldW0(seed=42), n=3, capture_id="meta")
    renamed = generate_episodes(RenamedWorld(seed=42), n=3, capture_id="meta")
    a = compile_behavior(base, name="meta")
    b = compile_behavior(renamed, name="meta")

    assert a.compiled.ir.to_dict() == b.compiled.ir.to_dict()
    # The concrete entity ids are abstracted away by compilation.
    assert "RENAMED-U042" not in str(b.compiled.ir.to_dict())


def test_duplicating_episodes_changes_support_only():
    world = WorldW0(seed=42)
    few = compile_behavior(generate_episodes(world, n=3, capture_id="meta"),
                           name="meta")
    many = compile_behavior(generate_episodes(world, n=6, capture_id="meta"),
                            name="meta")

    # Structure is unchanged ...
    assert few.compiled.ir.to_dict() == many.compiled.ir.to_dict()
    # ... only the evidence support (and episode count) grows.
    support_few = sorted(c.evidence.support for c in few.candidates)
    support_many = sorted(c.evidence.support for c in many.candidates)
    assert support_many == [s * 2 for s in support_few]
    assert many.package.evidence_summary["episode_count"] == 6
