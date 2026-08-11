"""The react leaf: native function-calling agent loop. No network — the model's
tool-calling turns are scripted as ModelTurns via FakeModel(turns=...)."""

from __future__ import annotations

import pytest

from jdsl import ModelTurn, RunContext, Status, ToolCall, react, root, tool
from jdsl.tree import _tool_schema


@tool
def lookup(city: str) -> str:
    """Return a fact about a city."""
    return {"Paris": "population 2.1M"}.get(city, "unknown")


def _ctx(model):
    return RunContext(model=model, model_id="deepseek-chat")


def test_calls_tool_then_answers(fake_model):
    model = fake_model(turns=[
        ModelTurn(tool_calls=[ToolCall(id="1", name="lookup", arguments={"city": "Paris"})]),
        ModelTurn(text="Paris has about 2.1M people."),
    ])
    node = react("question -> answer", tools=[lookup])
    ctx = _ctx(model)
    ctx.blackboard["question"] = "How big is Paris?"
    assert node.tick(ctx) is Status.SUCCESS
    assert ctx.blackboard["answer"] == "Paris has about 2.1M people."
    # the tool's observation was fed back into the second turn's history
    fed_back = model.converse_calls[1]["messages"]
    assert any(m["role"] == "tool" and "2.1M" in m["content"] for m in fed_back)


def test_answers_without_calling_tools(fake_model):
    model = fake_model(turns=[ModelTurn(text="42")])
    node = react("question -> answer", tools=[lookup])
    ctx = _ctx(model)
    assert node.tick(ctx) is Status.SUCCESS
    assert ctx.blackboard["answer"] == "42"
    assert len(model.converse_calls) == 1  # never looped


def test_max_steps_exhausted_fails(fake_model):
    looping = ModelTurn(tool_calls=[ToolCall(id="x", name="lookup", arguments={"city": "Paris"})])
    model = fake_model(turns=[looping])  # always calls, never answers
    node = react("question -> answer", tools=[lookup], max_steps=3)
    assert node.tick(_ctx(model)) is Status.FAILURE
    assert len(model.converse_calls) == 3


def test_empty_answer_fails(fake_model):
    model = fake_model(turns=[ModelTurn(text="   ")])
    assert react("q -> answer", tools=[lookup]).tick(_ctx(model)) is Status.FAILURE


def test_unknown_tool_is_reported_not_raised(fake_model):
    model = fake_model(turns=[
        ModelTurn(tool_calls=[ToolCall(id="1", name="nope", arguments={})]),
        ModelTurn(text="recovered"),
    ])
    ctx = _ctx(model)
    assert react("q -> answer", tools=[lookup]).tick(ctx) is Status.SUCCESS
    fed_back = model.converse_calls[1]["messages"]
    assert any(m["role"] == "tool" and "no tool named" in m["content"] for m in fed_back)


def test_multi_output_signature_rejected():
    with pytest.raises(ValueError, match="exactly one output"):
        react("q -> a, b", tools=[lookup])


def test_runs_through_root(fake_model):
    model = fake_model(turns=[
        ModelTurn(tool_calls=[ToolCall(id="1", name="lookup", arguments={"city": "Paris"})]),
        ModelTurn(text="done"),
    ])
    ctx = root("Agent", system="be terse").model("deepseek-chat").do(
        react("question -> answer", tools=[lookup])
    ).run(model=model, question="hi")
    assert ctx.blackboard["answer"] == "done"
    assert model.converse_calls[0]["system"] == "be terse"  # root system scoped in


# --- schema derivation -------------------------------------------------------

def test_tool_schema_types_and_required():
    def fn(a: str, b: int, c: float, d: bool, e="x"): ...
    schema = _tool_schema(fn)
    assert schema["properties"] == {
        "a": {"type": "string"}, "b": {"type": "integer"}, "c": {"type": "number"},
        "d": {"type": "boolean"}, "e": {"type": "string"},
    }
    assert schema["required"] == ["a", "b", "c", "d"]  # e has a default -> optional


def test_tool_schema_unannotated_defaults_to_string():
    def fn(x): ...
    assert _tool_schema(fn)["properties"]["x"] == {"type": "string"}


def test_tool_schema_list_becomes_array_with_items():
    def fn(nums: list[float], names: list[str], raw: list): ...
    props = _tool_schema(fn)["properties"]
    assert props["nums"] == {"type": "array", "items": {"type": "number"}}
    assert props["names"] == {"type": "array", "items": {"type": "string"}}
    assert props["raw"] == {"type": "array", "items": {"type": "string"}}  # bare list -> string items


def test_multi_tool_chain(fake_model):
    """A 3-step agent loop: two tool calls feeding a final answer — the shape the
    shop/db examples rely on."""
    @tool
    def double(n: int) -> int:
        """Double a number."""
        return n * 2

    model = fake_model(turns=[
        ModelTurn(tool_calls=[ToolCall(id="1", name="double", arguments={"n": 3})]),
        ModelTurn(tool_calls=[ToolCall(id="2", name="double", arguments={"n": 6})]),
        ModelTurn(text="12"),
    ])
    ctx = _ctx(model)
    assert react("q -> answer", tools=[double]).tick(ctx) is Status.SUCCESS
    assert ctx.blackboard["answer"] == "12"
    assert len(model.converse_calls) == 3  # looped twice, then answered
