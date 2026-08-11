"""The tracked Blackboard: provenance, overwrite (clobber) detection, coercion."""

from __future__ import annotations

from jdsl import Blackboard, RunContext


def test_set_records_writer_and_activity():
    bb = Blackboard()
    bb.set("category", "billing", writer="predict(msg -> category)")
    assert bb["category"] == "billing"
    assert bb.who_wrote("category") == "predict(msg -> category)"
    assert len(bb.activity) == 1
    assert bb.activity[0].previous is None


def test_overwrite_by_different_writer_is_flagged():
    bb = Blackboard()
    bb.set("x", 1, writer="a")
    bb.set("x", 2, writer="b")
    clob = bb.clobbers()
    assert len(clob) == 1
    assert (clob[0].key, clob[0].previous, clob[0].value, clob[0].writer) == ("x", 1, 2, "b")


def test_overwrite_by_same_writer_is_not_flagged():
    bb = Blackboard()
    bb.set("x", 1, writer="loop")
    bb.set("x", 2, writer="loop")  # a refine loop rewriting its own key is fine
    assert bb.clobbers() == []


def test_inputs_are_recorded_as_input_writer():
    bb = Blackboard({"seed": 42})
    assert bb.who_wrote("seed") == "input"


def test_plain_setitem_routes_through_tracking():
    bb = Blackboard()
    bb["k"] = "v"
    assert bb.who_wrote("k") == "?"
    assert bb["k"] == "v"


def test_runcontext_coerces_plain_dict_to_blackboard():
    ctx = RunContext(blackboard={"a": 1})
    assert isinstance(ctx.blackboard, Blackboard)
    assert ctx.blackboard.who_wrote("a") == "input"


def test_clobber_visible_after_a_run_of_two_leaves_sharing_a_key():
    # two distinct leaves writing the same key -> a real clobber (the silent bug).
    from jdsl import act, root, seq, store

    def fetch_a() -> str: return "first"
    def fetch_b() -> str: return "second"

    ctx = root("S").do(seq(
        store(act(fetch_a), "out"),
        store(act(fetch_b), "out"),
    )).run()
    assert ctx.blackboard["out"] == "second"
    assert [w.key for w in ctx.blackboard.clobbers()] == ["out"]
