"""Multi-turn Session: state persists across turns, offline. Both arms of the
determinism experiment are exercised here with a FakeModel (no network) —
flat/model-steered and tree/tree-steered."""

from __future__ import annotations

import pytest

from jdsl import Session, act, check, sel, seq, store, tool
from jdsl.context import ModelTurn, ToolCall


# -- flat / model-steered (the tau-bench "Arm A" baseline shape) --------------

def test_flat_persists_history_and_tool_state(fake_model):
    """Two user turns; a tool call in each mutates one shared env, and the
    conversation history from the first turn is still present in the second."""
    calls: list[int] = []

    @tool
    def bump() -> str:
        """Increment the shared counter."""
        calls.append(1)
        return f"count={len(calls)}"

    model = fake_model(turns=[
        ModelTurn(tool_calls=[ToolCall(id="1", name="bump", arguments={})]),
        ModelTurn(text="done 1"),
        ModelTurn(tool_calls=[ToolCall(id="2", name="bump", arguments={})]),
        ModelTurn(text="done 2"),
    ])
    s = Session(model=model, model_id="deepseek-chat", system="be terse", tools=[bump])

    assert s.send("first") == "done 1"
    assert s.send("second") == "done 2"

    assert len(calls) == 2                       # tool state accumulated across turns
    assert s.last_tool_calls == [{"name": "bump", "arguments": {}}]
    # the whole conversation is one growing history, not reset per turn
    users = [m for m in s.history if m["role"] == "user"]
    assert [m["content"] for m in users] == ["first", "second"]
    assert model.converse_calls[0]["system"] == "be terse"


def test_flat_tool_error_is_an_observation_not_a_crash(fake_model):
    @tool
    def boom() -> str:
        """Always fails."""
        raise RuntimeError("nope")

    model = fake_model(turns=[
        ModelTurn(tool_calls=[ToolCall(id="1", name="boom", arguments={})]),
        ModelTurn(text="recovered"),
    ])
    s = Session(model=model, model_id="deepseek-chat", tools=[boom])
    assert s.send("go") == "recovered"
    fed_back = model.converse_calls[1]["messages"]
    assert any(m["role"] == "tool" and "nope" in m["content"] for m in fed_back)


def test_flat_requires_exactly_one_mode(fake_model):
    with pytest.raises(ValueError, match="exactly one"):
        Session(model=fake_model(), tools=[], tree=seq())


# -- tree / tree-steered (the "Arm B" policy-in-the-tree shape) ---------------

def _refund_policy_tree():
    """Refunds are gated behind authentication *structurally*: the model can't
    reach the refund reply without the blackboard flag an earlier turn set."""
    return sel(
        seq(check("user_message", "authenticate"),
            store(act(lambda: True), "authed"),
            store(act(lambda: "authenticated"), "reply")),
        seq(check("user_message", "refund"),
            check("authed", True),
            store(act(lambda: "refunded"), "reply")),
        store(act(lambda: "please authenticate first"), "reply"),
    )


def test_tree_gates_state_across_turns(fake_model):
    # No model calls needed — the tree is deterministic — but Session requires one.
    s = Session(model=fake_model(), model_id="deepseek-chat", tree=_refund_policy_tree())

    assert s.send("refund") == "please authenticate first"   # blocked: not yet authed
    assert "authed" not in s.blackboard
    assert s.send("authenticate") == "authenticated"
    assert s.blackboard["authed"] is True                    # flag persists on the blackboard
    assert s.send("refund") == "refunded"                    # now the gate opens
