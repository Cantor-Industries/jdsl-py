"""The Arm-B retail policy tree (jdsl/bench/retail_policy.py), offline. The claim
under test is structural: the tools that would break policy are *not handed to the
model* until the guard holds — auth before any order tool, confirmation before any
write tool. We assert on the tool specs passed to `converse`, not just the reply,
because that unreachability is the determinism thesis."""

from __future__ import annotations

import json

from jdsl import ModelTurn, Session, ToolCall
from jdsl.bench.retail_policy import (
    _confirmed,
    _facts_builder,
    _known_facts,
    _last_user_line,
    _order_detail_lines,
    _order_ids,
    build_tree,
)
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


# -- surfacing the ids the tree already knows --------------------------------

def test_order_ids_and_known_facts_extraction():
    assert _order_ids("User: exchange #W2378156 and also #W1\nAgent: ok") == ["#W2378156", "#W1"]
    facts = _known_facts("yusuf_rossi_9620", "User: it's order #W2378156")
    assert "yusuf_rossi_9620" in facts and "#W2378156" in facts  # exact id, # preserved
    assert _known_facts(None, "no orders mentioned here") == ""


_ORDER_JSON = {
    "order_id": "#W2378156", "user_id": "yusuf_rossi_9620", "status": "delivered",
    "items": [
        {"name": "Mechanical Keyboard", "item_id": "1151293680", "product_id": "1656367028",
         "options": {"switch type": "linear", "backlight": "RGB"}},
        {"name": "Smart Thermostat", "item_id": "4983901480", "product_id": "4896585277", "options": {}},
    ],
    "payment_history": [{"transaction_type": "payment", "payment_method_id": "credit_card_9513926"}],
}


def _order_tool(payload) -> Tool:
    return Tool(fn=lambda **kw: json.dumps(payload) if isinstance(payload, dict) else payload,
                name="get_order_details", description="", parameters={"type": "object", "properties": {}})


def test_order_detail_lines_surface_item_ids_and_payment():
    lines = _order_detail_lines(_order_tool(_ORDER_JSON), "#W2378156")
    joined = "\n".join(lines)
    assert "1151293680" in joined and "4983901480" in joined  # current item_ids to exchange FROM
    assert "1656367028" in joined                             # product_id, for the variant lookup
    assert "credit_card_9513926" in joined                    # payment id, no re-derivation needed
    assert "switch type=linear" in joined                     # current options, so the model sees the delta


def test_order_detail_lines_tolerate_a_tool_error():
    assert _order_detail_lines(_order_tool("Error: order not found"), "#W1") == []


def test_facts_builder_folds_order_details_into_facts():
    facts = _facts_builder({"get_order_details": _order_tool(_ORDER_JSON)})("yusuf_rossi_9620",
                                                                            "User: exchange #W2378156")
    # the tree hands the execute-phase model every id it can't reliably reproduce
    for token in ("yusuf_rossi_9620", "#W2378156", "1151293680", "4983901480", "credit_card_9513926"):
        assert token in facts


def test_serve_phase_surfaces_verified_user_id_and_order_id(fake_model):
    """The tree hands the serve model the ids it already knows — the verified
    user_id (from the auth latch) and the order id the user named — so a small model
    quotes them exactly instead of guessing. Regression for the model sending
    'Yusuf Rossi, 19122' as a user_id and dropping the '#' from an order id."""
    s, model = _authed_session(fake_model)  # auth latch user_id is the tool's "ok"
    model.replies = ["cancel"]; model._i = 0
    model.turns = [ModelTurn(text="Order #W2378156 is pending. Shall I cancel it?")]; model._t = 0
    s.send("please cancel my order #W2378156")
    facts = s.blackboard.get("facts")
    assert "ok" in facts and "#W2378156" in facts
    # and the facts actually reached the model's prompt for that serve turn
    assert "#W2378156" in model.converse_calls[-1]["messages"][0]["content"]


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
