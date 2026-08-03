"""Multi-step support assistant: classify → route → draft a reply.

Exercises a multi-field signature, a `check` on model output, and a second
`predict` that consumes the first one's output (via the blackboard).

Run it:  uv run jdsl run examples/pipeline.py -i ticket="my card was charged twice"
"""

from jdsl import act, check, predict, root, sel, seq, tool


@tool
def page_oncall(): print("→ PAGED on-call (high urgency)")


@tool
def log_ticket(): print("→ logged (normal urgency)")


skill = (
    root("Support", system="You are a customer-support triage assistant.")
    .model("deepseek-chat")
    .do(
        seq(
            predict(
                "ticket -> category, urgency",
                instructions="category is one of: bug, billing, question. urgency is one of: low, high.",
            ),
            sel(
                seq(check("urgency", "high"), act(page_oncall)),
                act(log_ticket),
            ),
            predict(
                "ticket, category -> reply",
                instructions="Draft a short, friendly reply to the customer. Plain text.",
            ),
        )
    )
)


if __name__ == "__main__":
    ctx = skill.run(ticket=input("Describe the issue: "))
    print("category:", ctx.blackboard.get("category"))
    print("urgency :", ctx.blackboard.get("urgency"))
    print("reply   :", (ctx.blackboard.get("reply") or "")[:200])
