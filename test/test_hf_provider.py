"""HFModel contract test — no transformers/torch needed. We script `_complete`
(the only method that touches the model) and drive real jdsl leaves through it,
proving the local-model provider satisfies jdsl's generate/converse interface."""

from __future__ import annotations

from jdsl import RunContext, Session, Status, ToolCall, predict, react, tool
from jdsl.hf import HFModel


class ScriptedHF(HFModel):
    """HFModel with generation stubbed to a list of replies (in order). `native`
    selects which tool-calling path converse takes (prompt-based vs native)."""

    def __init__(self, replies: list[str], *, native: bool = False) -> None:
        self.replies = list(replies)
        self._i = 0
        self.max_new_tokens = 8
        self._call_id = 0
        self.model = None
        self.tokenizer = None
        self.native_tools = native

    def _next(self) -> str:
        r = self.replies[min(self._i, len(self.replies) - 1)]
        self._i += 1
        return r

    def _complete(self, chat: list[dict]) -> str:  # type: ignore[override]
        return self._next()

    def _complete_tools(self, chat: list[dict], tools: list[dict]) -> str:  # type: ignore[override]
        return self._next()


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


def test_native_tools_autodetected_for_gemma4():
    class Cfg: architectures = ["Gemma4ForConditionalGeneration"]; model_type = "gemma4"
    class M: config = Cfg()
    class Tok: chat_template = "…{{ tool_call }}…"
    assert HFModel(model=M(), tokenizer=Tok()).native_tools is True

    class PlainCfg: architectures = ["LlamaForCausalLM"]; model_type = "llama"
    class PlainM: config = PlainCfg()
    class PlainTok: chat_template = "no tool support"
    assert HFModel(model=PlainM(), tokenizer=PlainTok()).native_tools is False


def test_native_chat_shaping_keeps_roles_and_tool_calls():
    msgs = [
        {"role": "user", "content": "cancel W1"},
        {"role": "assistant", "content": "",
         "tool_calls": [ToolCall(id="1", name="get_order", arguments={"order_id": "#W1"})]},
        {"role": "tool", "tool_call_id": "1", "name": "get_order", "content": "ok"},
    ]
    chat = HFModel._to_native_chat("SYS", msgs)
    assert chat[0] == {"role": "system", "content": "SYS"}       # real system turn, not folded
    assert chat[2]["tool_calls"][0]["function"] == {"name": "get_order", "arguments": {"order_id": "#W1"}}
    assert chat[3] == {"role": "tool", "name": "get_order", "content": "ok"}


def test_native_parse_prefers_tool_call_markers():
    g = HFModel.__new__(HFModel)  # no model needed for the pure parser
    raw = 'Let me look.<|tool_call>{"name": "get_order", "arguments": {"order_id": "#W2378156"}}<tool_call|>'
    assert g._parse_native_tool_calls(raw) == [{"tool": "get_order", "arguments": {"order_id": "#W2378156"}}]
    assert g._clean_text("<|turn>model\nDone.<turn|>") == "model\nDone."
    # the quote token <|"|> leaks into Gemma's output too; it must not reach the user
    assert g._clean_text('Hello <|"|>there<|"|>.') == "Hello there."
    assert g._clean_text("Verified.<turn|><eos>") == "Verified."  # bare sentinels stripped too


def test_native_parse_handles_gemma_call_dsl():
    """Gemma 4 does not emit JSON inside the markers — it emits its own DSL,
    `call:NAME{key:<|"|>value<|"|>,…}`. This is the exact string observed from the
    real model; if it doesn't parse, no tool fires and the agent loops forever."""
    g = HFModel.__new__(HFModel)
    raw = ('<|tool_call>call:find_user_id_by_name_zip{first_name:<|"|>Yusuf<|"|>,'
           'last_name:<|"|>Rossi<|"|>,zip:<|"|>19122<|"|>}<tool_call|><|tool_response><eos>')
    assert g._parse_native_tool_calls(raw) == [
        {"tool": "find_user_id_by_name_zip",
         "arguments": {"first_name": "Yusuf", "last_name": "Rossi", "zip": "19122"}}]


def test_gemma_dsl_coerces_bracketed_list_args():
    """The model writes list args (item_ids, new_item_ids) in the DSL's own syntax —
    a bracketed string with quote tokens and internal commas. It must become a real
    list, or the tool rejects it with '[ not found'. Regression for exchange calls."""
    g = HFModel.__new__(HFModel)
    raw = ('<|tool_call>call:exchange_delivered_order_items{order_id:<|"|>#W2378156<|"|>,'
           'item_ids:[<|"|>1151293680<|"|>,<|"|>4983901480<|"|>],'
           'payment_method_id:<|"|>credit_card_9513926<|"|>}<tool_call|>')
    [call] = g._parse_native_tool_calls(raw)
    assert call["arguments"]["item_ids"] == ["1151293680", "4983901480"]  # a list, not a string
    assert call["arguments"]["order_id"] == "#W2378156"
    assert call["arguments"]["payment_method_id"] == "credit_card_9513926"


def test_gemma_dsl_preserves_hash_in_bare_value():
    """A value with no quote token (e.g. an order id) is taken bare — and its `#`
    must survive, since that prefix is exactly what tau-bench grades on."""
    g = HFModel.__new__(HFModel)
    raw = "<|tool_call>call:get_order_details{order_id:#W2378156}<tool_call|>"
    assert g._parse_native_tool_calls(raw) == [
        {"tool": "get_order_details", "arguments": {"order_id": "#W2378156"}}]


def test_native_react_loop_over_local_model():
    # native path: model emits a tool call (via markers), then a plain answer
    m = ScriptedHF(['<|tool_call>{"name": "lookup", "arguments": {"city": "Paris"}}<tool_call|>',
                    "Paris has 2.1M people."], native=True)
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
