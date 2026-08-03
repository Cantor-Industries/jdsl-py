"""Chain-of-thought: reason first, then answer (DSPy's ChainOfThought, as a tree).

Two chained `predict` leaves: the first thinks step by step into a `reasoning`
field, the second reads the question *and* that reasoning to produce a concise
`answer`. Classic trick question where naive answering trips up.

Run it:  uv run jdsl run examples/reason.py -i question="..."
"""

from jdsl import predict, root, seq

skill = (
    root("Reason", system="You are a careful, rigorous reasoner.")
    .model("deepseek-chat")
    .do(
        seq(
            predict("question -> reasoning", instructions="Think step by step. Show your work."),
            predict("question, reasoning -> answer", instructions="State ONLY the final answer, concisely."),
        )
    )
)


if __name__ == "__main__":
    q = "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much is the ball?"
    ctx = skill.run(question=q)
    print("reasoning:", (ctx.blackboard.get("reasoning") or "")[:400])
    print("answer   :", ctx.blackboard.get("answer"))
