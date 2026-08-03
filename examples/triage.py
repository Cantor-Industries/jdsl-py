"""The interesting case: the LLM actually drives the tree.

A ``predict`` leaf classifies an inbound message, writing ``category`` onto the
blackboard. A ``selector`` then tries branches in order; each branch is guarded
by a ``check`` on ``category``, so the model's output decides which action runs
(the last branch is an unguarded fallback). This is the synthesis the Python
rewrite is aiming at: behavior-tree determinism for control flow, a DSPy
signature for the LLM leaf.

The provider is inferred from the model id: ``deepseek-chat`` → DeepSeek,
``claude-*`` → Anthropic. A key is read from ``.env`` (``DEEPSEEK_API_KEY`` /
``ANTHROPIC_API_KEY``) or stored via ``jdsl config add``.

Run it:
    jdsl run examples/triage.py
"""

from jdsl import act, check, predict, root, sel, seq, store, tool


@tool
def inbound_message() -> str:
    """Stand-in for however a real message arrives (queue, webhook, stdin)."""
    return "I was double charged on my last invoice."


@tool
def route_to_billing() -> None:
    print("→ routed to BILLING")


@tool
def route_to_support() -> None:
    print("→ routed to SUPPORT")


@tool
def route_to_human() -> None:
    print("→ escalated to a HUMAN")


skill = (
    root(
        "Triage",
        system="You classify inbound customer messages. Categories: billing, support, other.",
    )
    .model("deepseek-chat")  # or "claude-opus-4-8" — provider is inferred from the id
    .do(
        seq(
            store(act(inbound_message), "message"),  # act result feeds the predict leaf
            predict(
                "message -> category",
                instructions="Classify into exactly one of: billing, support, other.",
            ),
            sel(
                seq(check("category", "billing"), act(route_to_billing)),
                seq(check("category", "support"), act(route_to_support)),
                act(route_to_human),  # fallback branch
            ),
        )
    )
)


if __name__ == "__main__":
    ctx = skill.run()
    print("category:", ctx.blackboard.get("category"))
