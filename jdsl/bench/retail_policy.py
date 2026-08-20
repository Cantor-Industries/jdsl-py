"""Arm B policy tree for tau-bench *retail* — the policy lives in the tree, not
in a prompt the model can talk its way around.

`build_tree(tools, wiki)` is what `jdsl.bench.tau_bench_adapter --arm tree` loads.
It returns a jdsl `Node` re-ticked once per user turn (the `Session` threads a
running `transcript` onto the blackboard, so a re-ticked tree still sees the whole
dialogue; the auth latch and other blackboard state persist across turns).

The thesis, made structural
----------------------------
The retail policy has two rules that a model-steered agent violates most: *verify
the user before doing anything*, and *never take a consequential action without
first restating it and getting an explicit "yes".* We do not ask the model nicely
to follow them — we make the tools that would break them **unreachable** until the
guard holds. Two phase-gates carry the whole reliability claim:

* **auth gate** — before a successful identity lookup the model is handed ONLY the
  two lookup tools. It *cannot* read or mutate an order because those tools are not
  in its hands. A successful lookup flips a latch (watched inside the wrapped auth
  tools); from the next turn the tree routes to the serve phase.

* **confirmation gate** — in the serve phase the tree first classifies the user's
  intent (`predict`), routes to that action's subtree, and there splits on whether
  the user has *already* confirmed. Until they have, the model gets read-only tools
  and can only gather details and propose; only once a deterministic check sees an
  affirmative reply does the tree expose that action's single write tool. A model
  that would otherwise cancel-before-confirming, or fire the wrong write tool,
  structurally can't.

So control (which phase, which action, may-we-write-yet) is the tree's
deterministic job; language (what did the user ask, what are the ids, how to phrase
the reply) is the model's. That split is the point of jdsl.
"""

from __future__ import annotations

import json
import re
from typing import Any

from jdsl import act, check, predict, react, ref, sel, seq, store
from jdsl.dsl import Tool

# tau-bench retail order ids have a fixed shape (#W followed by digits). Capturing
# the one the user named lets the tree hand the model an exact id to quote, rather
# than trusting a small model to reproduce it (it drops the '#').
_ORDER_ID = re.compile(r"#W\d+")

AUTH_TOOLS = ("find_user_id_by_email", "find_user_id_by_name_zip")

# Read-only tools, in scope for every serve-phase leaf (propose and execute alike).
# `think` is deliberately excluded: it is a no-op scratchpad, and a small model
# fills it with unbounded reasoning that overruns the token budget (so the tool call
# never closes and leaks to the user) and never converges to an action. Denying the
# escape hatch forces the model to either act or produce a real reply.
READ_TOOLS = ("get_order_details", "get_product_details", "get_user_details",
              "list_all_product_types", "calculate")

# Write tools, grouped by the intent that unlocks them. Each group is exposed only
# in its own action subtree, and only after confirmation — so the model can never
# reach for a write tool that doesn't match the action the user agreed to.
WRITE_TOOLS: dict[str, tuple[str, ...]] = {
    "cancel":   ("cancel_pending_order",),
    "modify":   ("modify_pending_order_address", "modify_pending_order_items",
                 "modify_pending_order_payment", "modify_user_address"),
    "return":   ("return_delivered_order_items",),
    "exchange": ("exchange_delivered_order_items",),
    "escalate": ("transfer_to_human_agents",),
}

INTENTS = tuple(WRITE_TOOLS)  # the write intents; anything else falls through to info

_AFFIRMATIVE = {"yes", "yeah", "yep", "yup", "correct", "confirm", "confirmed",
                "go ahead", "please do", "do it", "sounds good", "that's right", "ok", "okay"}

AUTH_INSTRUCTIONS = (
    "You are a retail support agent, and this conversation is NOT yet authenticated. "
    "Your only job right now is to verify who the user is. Ask for their email, or their "
    "full name and zip code, then call find_user_id_by_email or find_user_id_by_name_zip. "
    "Do not discuss orders, products, or take any other action until a lookup succeeds. "
    "When it succeeds, tell the user they are verified and ask how you can help. If a lookup "
    "fails, ask for the details again. Reply to the user in plain text."
)

INTENT_INSTRUCTIONS = (
    "The user is authenticated. Read the conversation and decide what they want to do RIGHT NOW. "
    "Answer with exactly one of these words and nothing else: "
    "cancel (cancel a pending order), modify (change a pending order or the user's address), "
    "return (return items from a delivered order), exchange (exchange items from a delivered "
    "order), escalate (hand off to a human), info (anything else — questions, lookups, chit-chat)."
)

PROPOSE_INSTRUCTIONS = (
    "The user wants to {intent} but has NOT confirmed yet, so you have only read-only tools. "
    "Look up the order and the exact items/ids involved, verify it belongs to THIS user and is in "
    "an eligible state, then restate to the user precisely what you will do and ask them to confirm "
    "with a yes. Do not claim the action is done — you cannot do it yet. Reply in plain text."
)

EXECUTE_INSTRUCTIONS = (
    "The user has confirmed a {intent}. Carry it out now with the write tool available to you, using "
    "the ids you looked up — do not invent ids. Take actions only for THIS user. If anything is "
    "still ambiguous, ask instead of guessing. When done, tell the user the outcome in plain text."
)

INFO_INSTRUCTIONS = (
    "Help the authenticated user with read-only tools: answer questions and look up orders, products, "
    "or their profile. Do not take any consequential action here. Reply in plain text."
)


def build_tree(tools: list[Tool], wiki: str) -> Any:
    """Assemble the retail Arm-B tree from the adapter-wrapped tau-bench tools."""
    by_name = {t.name: t for t in tools}
    latch = {"authenticated": False, "user_id": None}

    def pick(names: tuple[str, ...]) -> list[Tool]:
        return [by_name[n] for n in names if n in by_name]

    auth_tools = [_watch_auth(t, latch) for t in pick(AUTH_TOOLS)]
    read_tools = pick(READ_TOOLS)

    # Read the auth latch onto the blackboard so a `check` can branch on it. The
    # latch itself lives for the whole session inside the wrapped auth tools.
    sync_auth = store(act(lambda: latch["authenticated"]), "authenticated")
    # The verified user id is a fact the tree computed at auth time — surface it so
    # the serve model quotes it exactly instead of guessing from the transcript.
    sync_user = store(act(lambda: latch["user_id"]), "user_id")
    # Builds the serve-phase `facts` block: the ids the tree knows (user, order) plus
    # the order's live line items and payment id, read deterministically from tools.
    build_facts = _facts_builder(by_name)

    return sel(
        # --- serve phase: only reachable once authenticated --------------------
        seq(
            sync_auth,
            check("authenticated", True),
            sync_user,
            # Deterministic control decisions, set before any model leaf runs:
            store(act(build_facts, ref("user_id"), ref("transcript")), "facts"),  # ids to quote verbatim
            store(act(_confirmed, ref("transcript")), "confirmed"),  # has the user said yes?
            predict("transcript -> intent", instructions=INTENT_INSTRUCTIONS),  # what do they want?
            sel(
                *(_action(name, read_tools, pick(WRITE_TOOLS[name])) for name in INTENTS),
                # info / fallback: read-only, always answers so serve never falls back to auth.
                store(react("transcript, facts -> reply", tools=read_tools,
                            instructions=INFO_INSTRUCTIONS), "reply"),
            ),
        ),
        # --- auth phase: only the identity-lookup tools are in scope -----------
        seq(
            store(react("transcript -> reply", tools=auth_tools,
                        instructions=AUTH_INSTRUCTIONS, max_steps=6), "reply"),
            sync_auth,  # re-read so the flag is visible to the next turn / graders
        ),
    )


def _action(intent: str, read_tools: list[Tool], write_tools: list[Tool]) -> Any:
    """One write-intent subtree: reached when `intent` matches, then gated on
    confirmation. Confirmed -> the model gets this action's write tool(s) and does
    it; not yet -> read-only, gather and propose. The write tool is out of scope
    until the user has agreed, so the action can't fire early or by the wrong hand."""
    return seq(
        check("intent", intent),
        sel(
            seq(
                check("confirmed", True),
                store(react("transcript, facts -> reply", tools=read_tools + write_tools,
                            instructions=EXECUTE_INSTRUCTIONS.format(intent=intent)), "reply"),
            ),
            store(react("transcript, facts -> reply", tools=read_tools,
                        instructions=PROPOSE_INSTRUCTIONS.format(intent=intent)), "reply"),
        ),
    )


def _confirmed(transcript: Any) -> bool:
    """True iff the user's most recent line is an affirmative — a deterministic
    read of the transcript, not a model judgement, so the write gate can't be
    talked open. Confirmation is a control decision; the tree owns it."""
    line = _last_user_line(transcript)
    if not line: return False
    norm = line.strip().strip(".!?,;:\"'").casefold()
    return norm in _AFFIRMATIVE or any(norm.startswith(a) for a in _AFFIRMATIVE)


def _last_user_line(transcript: Any) -> str:
    """The text of the last `User:` line the Session appended to the transcript."""
    if not transcript: return ""
    for line in reversed(str(transcript).splitlines()):
        if line.startswith("User:"): return line[len("User:"):].strip()
    return ""


def _order_ids(transcript: Any) -> list[str]:
    """Order ids the user named, in tau-bench's fixed #W... format, de-duped in order."""
    return list(dict.fromkeys(_ORDER_ID.findall(str(transcript or ""))))


def _known_facts(user_id: Any, transcript: Any, extra_lines: tuple[str, ...] = ()) -> str:
    """The ids the tree already knows for certain — the verified user id (computed at
    auth time), the order ids the user named, and (via `extra_lines`) the order's
    current items and payment id — rendered for the serve model to quote *verbatim*.
    A small model drops the '#', forgets its user id, and writes placeholder item ids;
    handing it these removes the brittle copying and leaves it only the language. This
    is deterministic state flowing to the model, not hardcoding: the values come from
    the auth step, the user's words, and live tool reads — never the episode answer."""
    lines = []
    if user_id:
        lines.append(f"authenticated user_id = {user_id}")
    lines += [f"order id in question = {oid}" for oid in _order_ids(transcript)]
    lines += list(extra_lines)
    if not lines:
        return ""
    return ("Known-good values from the system — use these EXACT ids in tool calls; "
            "never invent, reformat, abbreviate, or use placeholder ids:\n"
            + "\n".join(f"- {ln}" for ln in lines))


def _order_detail_lines(get_order: Tool, order_id: str) -> list[str]:
    """Read the order deterministically and render its current line items (name +
    item_id + product_id + options) and the payment id, so the execute-phase model
    has the ids it must exchange FROM without re-deriving them. The model still picks
    the target variants (the semantic part) — the tree just supplies the raw ids."""
    try:
        data = json.loads(get_order.fn(order_id=order_id))
    except (json.JSONDecodeError, TypeError):
        return []  # an "Error: ..." string or a non-JSON return: nothing to surface
    if not isinstance(data, dict):
        return []
    lines = []
    for item in data.get("items") or []:
        opts = item.get("options") or {}
        suffix = f" [{', '.join(f'{k}={v}' for k, v in opts.items())}]" if opts else ""
        lines.append(f"current item: {item.get('name')} — item_id {item.get('item_id')}, "
                     f"product_id {item.get('product_id')}{suffix}")
    pay = _payment_method_id(data)
    if pay:
        lines.append(f"payment_method_id for the exchange = {pay}")
    return lines


def _payment_method_id(order: dict) -> str:
    """The payment method the order was paid with — what an exchange charges/refunds to."""
    for entry in order.get("payment_history") or []:
        if entry.get("payment_method_id"):
            return str(entry["payment_method_id"])
    return ""


def _facts_builder(by_name: dict[str, Tool]) -> Any:
    """A `facts` builder closed over the toolset, so the tree can deterministically
    read the named order and fold its item ids and payment id into the facts it hands
    the serve model — alongside the user id and order id it already surfaces."""
    get_order = by_name.get("get_order_details")

    def build(user_id: Any, transcript: Any) -> str:
        extra: list[str] = []
        orders = _order_ids(transcript)
        if get_order is not None and orders:
            extra = _order_detail_lines(get_order, orders[0])
        return _known_facts(user_id, transcript, tuple(extra))

    return build


def _watch_auth(tool: Tool, latch: dict[str, Any]) -> Tool:
    """Wrap an identity-lookup tool so a successful call flips the auth latch.
    tau-bench's find tools return the user id on success, or an 'Error: ...' string
    on failure — so success is 'came back non-empty and not an error'."""
    inner = tool.fn

    def fn(**kwargs: Any) -> Any:
        result = inner(**kwargs)
        text = str(result).strip()
        if text and not text.lower().startswith("error"):
            latch["authenticated"] = True
            latch["user_id"] = text
        return result

    return Tool(fn=fn, name=tool.name, description=tool.description, parameters=tool.parameters)
