"""Arm B policy tree for tau-bench *retail* — policy encoded in the tree, not
just the prompt.

`build_tree(tools, wiki)` is what `jdsl.bench.tau_bench_adapter --arm tree` loads.
It returns a jdsl `Node` re-ticked once per user turn (the `Session` threads a
running `transcript` onto the blackboard so a re-ticked tree still sees the whole
dialogue).

The structural guarantee
------------------------
The retail policy's first and most-violated rule is: *authenticate the user
before doing anything else.* We enforce that by **tool availability per phase**,
not by asking the model nicely:

* **Before authentication** the model is handed ONLY the two identity-lookup
  tools. It physically cannot cancel an order or read another user's data,
  because those tools are not in its hands yet.
* A successful lookup flips a latch (watched inside the wrapped auth tools), and
  from the next turn on the tree routes to the **serve** phase with the full
  toolset.

That is the determinism thesis in one gate: a weak model that would otherwise
skip or fumble authentication *can't*, because the tree removed the option.
Everything downstream of auth (confirm-before-write, status checks) is still
reinforced as instructions here — extending the same phase-gating to a
confirmation latch is the natural next iteration, noted at the bottom.
"""

from __future__ import annotations

from typing import Any

from jdsl import act, check, react, sel, seq, store
from jdsl.dsl import Tool

AUTH_TOOLS = ("find_user_id_by_email", "find_user_id_by_name_zip")

READ_TOOLS = ("get_order_details", "get_product_details", "get_user_details",
              "list_all_product_types", "calculate", "think")

WRITE_TOOLS = ("cancel_pending_order", "modify_pending_order_address",
               "modify_pending_order_items", "modify_pending_order_payment",
               "modify_user_address", "return_delivered_order_items",
               "exchange_delivered_order_items")

ESCALATE_TOOLS = ("transfer_to_human_agents",)

AUTH_INSTRUCTIONS = (
    "You are a retail support agent, and this conversation is NOT yet authenticated. "
    "Your only job right now is to verify who the user is. Ask for their email, or "
    "their full name and zip code, then call find_user_id_by_email or "
    "find_user_id_by_name_zip. Do not discuss orders, products, or take any other "
    "action until a lookup succeeds. When it succeeds, greet the user by acknowledging "
    "they are verified and ask how you can help. If a lookup fails, ask for the details "
    "again. Reply to the user in plain text."
)

SERVE_INSTRUCTIONS = (
    "The user is authenticated. Follow the retail policy exactly. Before ANY "
    "consequential action (cancel, modify, return, exchange), first look up the order "
    "and check its status, then restate the exact details to the user and get an "
    "explicit 'yes' before calling the write tool. Only take actions for THIS user. "
    "Do not invent order ids, item ids, or facts — look them up. When you are ready to "
    "speak to the user, reply in plain text."
)


def build_tree(tools: list[Tool], wiki: str) -> Any:
    """Assemble the retail Arm-B tree from the adapter-wrapped tau-bench tools."""
    by_name = {t.name: t for t in tools}
    latch = {"authenticated": False, "user_id": None}

    def pick(names: tuple[str, ...]) -> list[Tool]:
        return [by_name[n] for n in names if n in by_name]

    auth_tools = [_watch_auth(t, latch) for t in pick(AUTH_TOOLS)]
    serve_tools = pick(READ_TOOLS + WRITE_TOOLS + ESCALATE_TOOLS)

    # Read the latch onto the blackboard so a `check` can branch on it. Runs each
    # tick; the latch itself lives for the whole session inside the wrapped tools.
    sync_latch = store(act(lambda: latch["authenticated"]), "authenticated")

    return sel(
        # --- serve phase: only reachable once authenticated ------------------
        seq(
            sync_latch,
            check("authenticated", True),
            store(react("transcript -> reply", tools=serve_tools,
                        instructions=SERVE_INSTRUCTIONS, max_steps=20), "reply"),
        ),
        # --- auth phase: only the identity-lookup tools are in scope ---------
        seq(
            store(react("transcript -> reply", tools=auth_tools,
                        instructions=AUTH_INSTRUCTIONS, max_steps=6), "reply"),
            sync_latch,  # re-read so the flag is visible to graders/next turn
        ),
    )


def _watch_auth(tool: Tool, latch: dict[str, Any]) -> Tool:
    """Wrap an identity-lookup tool so a successful call flips the auth latch.
    tau-bench's find tools return the user id on success, or an 'Error: ...'
    string on failure — so success is 'came back non-empty and not an error'."""
    inner = tool.fn

    def fn(**kwargs: Any) -> Any:
        result = inner(**kwargs)
        text = str(result).strip()
        if text and not text.lower().startswith("error"):
            latch["authenticated"] = True
            latch["user_id"] = text
        return result

    return Tool(fn=fn, name=tool.name, description=tool.description, parameters=tool.parameters)


# Next iteration: a second phase-gate for confirmation — expose WRITE_TOOLS only
# after a "confirmed" latch is set (the model states details, the user says yes),
# so consequential writes are structurally impossible before an explicit yes.
