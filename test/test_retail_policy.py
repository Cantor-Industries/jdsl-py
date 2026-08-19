"""The Arm-B retail policy tree (jdsl/bench/retail_policy.py), offline. The claim
under test is structural: the tools that would break policy are *not handed to the
model* until the guard holds — auth before any order tool, confirmation before any
write tool. We assert on the tool specs passed to `converse`, not just the reply,
because that unreachability is the determinism thesis."""

from __future__ import annotations

from jdsl import ModelTurn, Session, ToolCall
from jdsl.bench.retail_policy import _confirmed, _last_user_line, build_tree
from jdsl.dsl import Tool

_TOOL_NAMES = (
    "find_user_id_by_email", "find_user_id_by_name_zip",
    "get_order_details", "get_product_details", "get_user_details",
    "list_all_product_types", "calculate", "think",
    "cancel_pending_order", "modify_pending_order_address", "modify_pending_order_items",
    "modify_pending_order_payment", "modify_user_address",
    "return_delivered_order_items", "exchange_delivered_order_items", "transfer_to_human_agents",
)


def _tools() -> list[Tool]:
    # tau-bench tools arrive as **kwargs bridges carrying an explicit schema.
    return [Tool(fn=lambda **kw: "ok", name=n, description=n,
                 parameters={"type": "object", "properties": {}}) for n in _TOOL_NAMES]


def _tool_names_last_converse(model) -> set[str]:
    return {t["name"] for t in model.converse_calls[-1]["tools"]}


# -- the deterministic confirmation gate -------------------------------------

def test_confirmed_reads_only_the_last_user_line():
    assert _last_user_line("Agent: cancel #W1?\nUser: yes") == "yes"
    assert _confirmed("Agent: cancel #W1?\nUser: yes, go ahead") is True
    assert _confirmed("Agent: cancel #W1?\nUser: what's the price first?") is False
    # an earlier yes doesn't leak: only the latest user line counts
    assert _confirmed("User: yes\nAgent: anything else?\nUser: no thanks") is False
    assert _confirmed(None) is False


# -- auth gate ---------------------------------------------------------------

def test_auth_phase_exposes_only_lookup_tools(fake_model):
    # Model tries to answer straight away (no tool call); tree is still in auth phase.
    model = fake_model(turns=[ModelTurn(text="How can I help?")])
    s = Session(model=model, model_id="local", tree=build_tree(_tools(), "wiki"))
    s.send("I want to cancel order #W1")
    offered = _tool_names_last_converse(model)
    assert offered == {"find_user_id_by_name_zip", "find_user_id_by_email"}
    assert "cancel_pending_order" not in offered  # order tools are unreachable pre-auth
    assert s.blackboard.get("authenticated") is False


def test_successful_lookup_flips_the_auth_latch(fake_model):
    model = fake_model(turns=[
        ModelTurn(tool_calls=[ToolCall(id="1", name="find_user_id_by_name_zip",
                                       arguments={"first_name": "Yusuf", "last_name": "Rossi", "zip": "19122"})]),
        ModelTurn(text="You're verified — how can I help?"),
    ])
    s = Session(model=model, model_id="local", tree=build_tree(_tools(), "wiki"))
    reply = s.send("Yusuf Rossi, 19122")
    assert s.blackboard.get("authenticated") is True
    assert "verified" in reply


# -- confirmation gate (post-auth) -------------------------------------------

def _authed_session(fake_model):
    """A session already past the auth gate, ready for serve-phase turns."""
    model = fake_model(turns=[
        ModelTurn(tool_calls=[ToolCall(id="1", name="find_user_id_by_email",
                                       arguments={"email": "y@x.com"})]),
        ModelTurn(text="verified"),
    ])
    s = Session(model=model, model_id="local", tree=build_tree(_tools(), "wiki"))
    s.send("my email is y@x.com")
    assert s.blackboard.get("authenticated") is True
    return s, model


def test_unconfirmed_write_intent_gets_read_only_tools(fake_model):
    s, model = _authed_session(fake_model)
    # serve turn: predict -> intent "cancel"; react answers (proposes) without a write.
    model.replies = ["cancel"]; model._i = 0
    model.turns = [ModelTurn(text="Order #W1 is pending. Shall I cancel it?")]; model._t = 0
    s.send("please cancel order #W1")
    assert s.blackboard.get("intent") == "cancel"
    assert s.blackboard.get("confirmed") is False
    offered = _tool_names_last_converse(model)
    assert "cancel_pending_order" not in offered  # the write tool is NOT in the model's hands
    assert offered.issubset(set(_TOOL_NAMES[2:8]))  # only READ_TOOLS


def test_confirmed_write_intent_unlocks_the_single_write_tool(fake_model):
    s, model = _authed_session(fake_model)
    model.replies = ["cancel"]; model._i = 0
    model.turns = [
        ModelTurn(tool_calls=[ToolCall(id="1", name="cancel_pending_order", arguments={"order_id": "W1"})]),
        ModelTurn(text="Done — order #W1 is cancelled."),
    ]; model._t = 0
    reply = s.send("yes, go ahead")
    assert s.blackboard.get("confirmed") is True
    offered = _tool_names_last_converse(model)
    assert "cancel_pending_order" in offered            # unlocked by confirmation
    assert "return_delivered_order_items" not in offered  # but only THIS action's write tool
    assert "cancelled" in reply
