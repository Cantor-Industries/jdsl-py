"""Classify and route a message with Jev inside a JDSL behavior tree.

Requires ``uv add typesafe-sdk`` and ``TYPESAFE_API_KEY`` in the environment.
Run with ``uv run jdsl run examples/triage_jev.py -i message="I was charged twice"``
or run this file directly to use the sample message below.
"""

from typesafe_sdk import Choice, TypeSafeClient

from jdsl import act, check, ref, root, sel, seq, store, tool


@tool
def jev_classify(message: str) -> str:
    """Ask Jev to choose the best category for an inbound message."""
    with TypeSafeClient(model="jev-latest") as client:
        result = client.system_one(
            {"message": message},
            {
                "category": Choice(
                    instructions="Which team should handle this message?",
                    criteria={
                        "billing": "Charges, invoices, and payment problems",
                        "support": "Product or service problems",
                        "other": "Does not fit billing or support",
                    },
                ),
            },
        )
    return result.answers["category"].choice


@tool
def route_to_billing() -> None:
    print("routed to BILLING")


@tool
def route_to_support() -> None:
    print("routed to SUPPORT")


@tool
def route_to_human() -> None:
    print("escalated to a HUMAN")


skill = root("Jev triage").do(
    seq(
        store(act(jev_classify, ref("message")), "category"),
        sel(
            seq(check("category", "billing"), act(route_to_billing)),
            seq(check("category", "support"), act(route_to_support)),
            act(route_to_human),
        ),
    )
)


if __name__ == "__main__":
    ctx = skill.run(message="I was double charged on my last invoice.")

    print("category:", ctx.blackboard.get("category"))
    print("blackboard:", ctx.blackboard)
