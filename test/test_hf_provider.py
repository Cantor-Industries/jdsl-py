"""HFModel contract test — no transformers/torch needed. We script `_complete`
(the only method that touches the model) and drive real jdsl leaves through it,
proving the local-model provider satisfies jdsl's generate/converse interface."""

from __future__ import annotations

from jdsl import RunContext, Session, Status, predict, react, tool
from jdsl.hf import HFModel


class ScriptedHF(HFModel):
    """HFModel with generation stubbed to a list of replies (in order)."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self._i = 0
        self.max_new_tokens = 8
        self._call_id = 0
        self.model = None
        self.tokenizer = None

    def _complete(self, chat: list[dict]) -> str:  # type: ignore[override]
        r = self.replies[min(self._i, len(self.replies) - 1)]
        self._i += 1
        return r


@tool
def lookup(city: str) -> str:
    """Return a fact about a city."""
    return {"Paris": "2.1M"}.get(city, "unknown")


def test_react_loop_over_local_model():
    # first turn: a tool call as JSON; second turn: the plain-text answer
    m = ScriptedHF(['{"tool": "lookup", "arguments": {"city": "Paris"}}', "Paris has 2.1M people."])
    ctx = RunContext(model=m, model_id="local")
    ctx.blackboard["question"] = "how big is paris?"
    assert react("question -> answer", tools=[lookup]).tick(ctx) is Status.SUCCESS
    assert "2.1M" in ctx.blackboard["answer"]


def test_parses_tool_call_wrapped_in_prose_with_nested_args():
    """The model often narrates before emitting the call, and the args are a nested
    object. The brace-balanced extractor must still find it — a non-greedy regex
    stops at the first inner '}' and the JSON (a real tool call) leaks to the user."""
    text = ('I understand. I will now look up your order.\n\n'
            '{"tool": "get_order_details", "arguments": {"order_id": "#W2378156"}}')
    call = HFModel._parse_tool_call(text)
    assert call == {"tool": "get_order_details", "arguments": {"order_id": "#W2378156"}}


def test_parse_ignores_braces_inside_strings():
    text = '{"tool": "say", "arguments": {"msg": "use {curly} braces"}}'
    assert HFModel._parse_tool_call(text)["arguments"] == {"msg": "use {curly} braces"}


def test_plain_answer_is_not_a_tool_call():
    assert HFModel._parse_tool_call("Sorry, I couldn't find that order.") is None


def test_react_over_local_model_parses_prose_wrapped_call():
    # first turn narrates + emits the call as prose; second turn is the plain answer
    m = ScriptedHF(['Let me check.\n{"tool": "lookup", "arguments": {"city": "Paris"}}',
                    "Paris has 2.1M people."])
    ctx = RunContext(model=m, model_id="local")
    ctx.blackboard["question"] = "how big is paris?"
    assert react("question -> answer", tools=[lookup]).tick(ctx) is Status.SUCCESS
    assert "2.1M" in ctx.blackboard["answer"]


def test_predict_over_local_model():
    m = ScriptedHF(["billing"])
    ctx = RunContext(model=m, model_id="local")
    ctx.blackboard["message"] = "I was double charged"
    assert predict("message -> category").tick(ctx) is Status.SUCCESS
    assert ctx.blackboard["category"] == "billing"


def test_multi_turn_session_over_local_model():
    m = ScriptedHF([
        '{"tool": "lookup", "arguments": {"city": "Paris"}}', "It's 2.1M.",  # turn 1
        "Still 2.1M.",                                                        # turn 2
    ])
    s = Session(model=m, model_id="local", system="be terse", tools=[lookup])
    assert "2.1M" in s.send("population of paris?")
    assert "2.1M" in s.send("and again?")
    # history persisted across the two user turns
    users = [x["content"] for x in s.history if x["role"] == "user"]
    assert users == ["population of paris?", "and again?"]
