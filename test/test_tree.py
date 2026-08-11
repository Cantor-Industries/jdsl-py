"""Interpreter semantics: how nodes tick and combine. No network."""

from __future__ import annotations

import pytest

from jdsl import RunContext, Status, act, check, predict, ref, root, sel, seq, store, tool


def _ctx_with(model):
    return RunContext(model=model, model_id="deepseek-chat")


def test_sequence_runs_children_in_order():
    calls: list[str] = []
    root("S").do(seq(act(lambda: calls.append("a")), act(lambda: calls.append("b")))).run()
    assert calls == ["a", "b"]


def test_sequence_fails_fast():
    calls: list[str] = []

    def boom() -> Status:
        calls.append("boom")
        return Status.FAILURE

    root("S").do(seq(act(boom), act(lambda: calls.append("never")))).run()
    assert calls == ["boom"]


def test_selector_stops_at_first_success():
    calls: list[str] = []
    root("S").do(
        sel(
            act(lambda: (calls.append("x"), Status.FAILURE)[1]),
            act(lambda: calls.append("y")),
            act(lambda: calls.append("never")),
        )
    ).run()
    assert calls == ["x", "y"]


def test_selector_all_fail_returns_failure():
    node = sel(act(lambda: Status.FAILURE), act(lambda: Status.FAILURE))
    assert node.tick(RunContext()) is Status.FAILURE


def test_check_true_and_false_paths():
    hit: list[str] = []
    root("S").do(
        sel(
            seq(check("category", "support"), act(lambda: hit.append("support"))),
            act(lambda: hit.append("fallback")),
        )
    ).run(category="billing")
    assert hit == ["fallback"]  # support check failed, fell through


@pytest.mark.parametrize("value", ["yes", "Yes", "YES", " yes ", "yes.", '"yes"', "Yes!"])
def test_check_matches_fuzzy_model_text(value):
    # model text varies in case/whitespace/punctuation; check must still match.
    assert check("ok", "yes").tick(RunContext(blackboard={"ok": value})) is Status.SUCCESS


def test_check_still_distinguishes_different_values():
    assert check("ok", "yes").tick(RunContext(blackboard={"ok": "no"})) is Status.FAILURE


def test_check_non_string_compares_exactly():
    # normalization is string-only; ints and the like stay plain ==.
    assert check("n", 2).tick(RunContext(blackboard={"n": 2})) is Status.SUCCESS
    assert check("n", 2).tick(RunContext(blackboard={"n": "2"})) is Status.FAILURE


def test_action_return_value_stored():
    ctx = root("S").do(seq(store(act(lambda: 42), "answer"))).run()
    assert ctx.blackboard["answer"] == 42


def test_ref_resolves_from_blackboard():
    seen: list[str] = []
    root("S").do(seq(act(seen.append, ref("query")))).run(query="hello")
    assert seen == ["hello"]


def test_ref_missing_key_raises():
    with pytest.raises(KeyError, match="not on the blackboard"):
        act(lambda x: x, ref("missing")).tick(RunContext())


def test_root_without_child_raises():
    with pytest.raises(RuntimeError, match="has no child"):
        root("S").tick(RunContext())


def test_context_is_scoped_to_subtree(fake_model):
    model = fake_model('{"answer": "42"}')
    skill = (
        root("S", system="root-level")
        .model("deepseek-chat")
        .do(seq(predict("q -> answer", context="leaf-level")))
    )
    skill.run(model=model, q="?")
    system = model.calls[0]["system"]
    assert "root-level" in system and "leaf-level" in system


# --- the LLM leaf, driven by a fake model -----------------------------------

def test_predict_writes_outputs_and_drives_selector(fake_model):
    model = fake_model("billing")  # single output -> stored verbatim
    hit: list[str] = []
    skill = (
        root("Triage", system="classify")
        .model("deepseek-chat")
        .do(
            seq(
                predict("message -> category"),
                sel(
                    seq(check("category", "billing"), act(lambda: hit.append("billing"))),
                    act(lambda: hit.append("fallback")),
                ),
            )
        )
    )
    ctx = skill.run(model=model, message="double charged")
    assert ctx.blackboard["category"] == "billing"
    assert hit == ["billing"]
    assert model.calls[0]["model_id"] == "deepseek-chat"
    assert "classify" in model.calls[0]["system"]


def test_single_output_stored_verbatim(fake_model):
    model = fake_model("  the ball costs $0.05  ")
    ctx = root("S").model("deepseek-chat").do(seq(predict("q -> answer"))).run(model=model, q="?")
    assert ctx.blackboard["answer"] == "the ball costs $0.05"  # stripped, not JSON-parsed
    assert "JSON object" not in model.calls[0]["messages"][0]["content"]  # single output: no JSON envelope


def test_single_output_empty_reply_is_failure(fake_model):
    model = fake_model("   ")
    assert predict("q -> answer").tick(_ctx_with(model)) is Status.FAILURE


def test_multi_output_parses_json(fake_model):
    model = fake_model('Sure! Here:\n{"a": "1", "b": "2"}\nHope that helps.')
    ctx = root("S").model("deepseek-chat").do(seq(predict("m -> a, b"))).run(model=model, m="x")
    assert ctx.blackboard["a"] == "1" and ctx.blackboard["b"] == "2"
    assert "JSON object" in model.calls[0]["messages"][0]["content"]  # multi output: JSON envelope


def test_multi_output_unparseable_is_failure(fake_model):
    model = fake_model("not json at all")
    hit: list[str] = []
    skill = (
        root("S")
        .model("deepseek-chat")
        .do(sel(seq(predict("m -> a, b"), act(lambda: hit.append("ok"))), act(lambda: hit.append("fail"))))
    )
    skill.run(model=model, m="x")
    assert hit == ["fail"]  # predict FAILUREd, selector fell through


def test_predict_without_model_raises():
    with pytest.raises(RuntimeError, match="no model is attached"):
        predict("m -> answer").tick(RunContext())


def test_chained_predicts_are_stateless(fake_model):
    # each predict sends exactly one user message — no accumulated assistant
    # history (which would 400 on Anthropic and leak prior output).
    model = fake_model("1", "2")
    root("S").model("deepseek-chat").do(seq(predict("x -> a"), predict("a -> b"))).run(model=model, x="in")
    for call in model.calls:
        assert len(call["messages"]) == 1
        assert call["messages"][0]["role"] == "user"


def test_tool_may_signal_failure_to_selector():
    @tool
    def always_fail() -> Status:
        return Status.FAILURE

    hit: list[str] = []
    root("S").do(sel(act(always_fail), act(lambda: hit.append("fallback")))).run()
    assert hit == ["fallback"]
