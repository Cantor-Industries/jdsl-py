"""Probe small-step `predict` leaves on Tinker's Inkling base model.

Inkling is not instruction-tuned; the raw output may not follow a leaf's
instructions, and a successful `predict` status does not validate correctness.

Run: uv run jdsl run examples/tinker.py -i question="..."
Or:  uv run python examples/tinker.py
Requires TINKER_API_KEY in the environment or `.env`.
"""

from jdsl import predict, root, seq

skill = (
    root("Tinker small steps", system="Work only on the current step. Be concise.")
    .model("thinkingmachines/Inkling")
    .do(
        seq(
            predict(
                "question -> quantities",
                instructions=(
                    "Extract the initial total and amount removed. Write exactly: "
                    "total=<integer>; removed=<integer>."
                ),
            ),
            predict(
                "quantities -> answer",
                instructions=(
                    "Subtract the amount removed from the initial total. "
                    "Reply with only the resulting integer."
                ),
            ),
        )
    )
)


if __name__ == "__main__":
    question = "A shop receives 3 boxes with 8 apples in each, then sells 5. How many apples remain?"
    context = skill.run(question=question)
    print("quantities:", context.blackboard.get("quantities"))
    print("raw answer:", (context.blackboard.get("answer") or "")[:400])
