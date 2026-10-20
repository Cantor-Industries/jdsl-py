"""A confidence-aware Socratic tutor using Jev judgments and JDSL policy.

Requires ``uv add typesafe-sdk`` and ``TYPESAFE_API_KEY`` in the environment.
Run with:

    uv run jdsl run examples/tutor_socratic.py \
      -i question="Solve 2x + 3 = 11" -i expected_answer="x = 4" \
      -i student_answer="2x = 8, so x = 8"
"""

from typesafe_sdk import Choice, TypeSafeClient

from jdsl import act, guard, ref, root, sel, seq, store, tool

LOW_CONFIDENCE_THRESHOLD = 0.6


@tool
def jev_assess(question: str, expected_answer: str, student_answer: str) -> dict:
    """Get typed correctness and misconception judgments, including confidence."""
    with TypeSafeClient(model="jev-latest") as client:
        result = client.system_one(
            {
                "question": question,
                "expected_answer": expected_answer,
                "student_answer": student_answer,
            },
            {
                "correctness": Choice(
                    instructions="How correct is the student's answer?",
                    criteria={
                        "correct": "The final answer and shown reasoning are correct.",
                        "partially_correct": (
                            "Some reasoning is correct, but the work is incomplete or has a small error."
                        ),
                        "incorrect": "The answer or reasoning shows a substantive error.",
                    },
                ),
                "misconception": Choice(
                    instructions="What best describes the main misconception in the student's work?",
                    criteria={
                        "arithmetic_error": "The method is reasonable, but a numerical calculation is wrong.",
                        "inverse_operation": "An operation is undone incorrectly or applied to only one side.",
                        "variable_isolation": "The student has not correctly isolated the variable.",
                        "sign_error": "A positive or negative sign is mishandled.",
                        "none_identified": "No clear misconception is present in the work.",
                        "unclear": "The work does not provide enough evidence to identify a misconception.",
                    },
                ),
            },
        )

    correctness = result.answers["correctness"]
    misconception = result.answers["misconception"]
    return {
        "correctness": {
            "choice": correctness.choice,
            "confidence": correctness.confidence,
        },
        "misconception": {
            "choice": misconception.choice,
            "confidence": misconception.confidence,
        },
    }


@tool
def ask_for_reasoning(question: str, student_answer: str) -> None:
    print(
        f"I'm not sure I understand your approach to {question!r}. "
        f"Can you show the steps that led to {student_answer!r}?"
    )


@tool
def acknowledge_correct() -> None:
    print("That looks right. Can you explain why that step works?")


@tool
def ask_next_step(misconception: str) -> None:
    prompts = {
        "arithmetic_error": "Which arithmetic step could you check another way?",
        "inverse_operation": "What operation would undo that step, and should it apply to both sides?",
        "variable_isolation": "What is still being done to the variable, and how could you undo it?",
        "sign_error": "Can you check how the sign changes in that step?",
        "none_identified": "Can you explain the next step you would try?",
        "unclear": "Can you show one more step of your reasoning?",
    }
    print(prompts.get(misconception, "What would you try as the next step?"))


@tool
def explore_error(misconception: str) -> None:
    prompts = {
        "arithmetic_error": "Where might the arithmetic have changed the result?",
        "inverse_operation": "How can you undo that operation while keeping both sides equal?",
        "variable_isolation": "What operation remains between the variable and its value?",
        "sign_error": "At which step might the sign have changed?",
        "none_identified": "Can you substitute your answer back into the original question?",
        "unclear": "Could you write out the steps so we can inspect them together?",
    }
    print(prompts.get(misconception, "Which step would you like to check first?"))


skill_tutor = root(
    "Confidence-aware Socratic tutor",
    system="Use Jev's typed assessment as evidence; JDSL owns the tutoring policy.",
).do(
    seq(
        store(
            act(
                jev_assess,
                ref("question"),
                ref("expected_answer"),
                ref("student_answer"),
            ),
            "assessment",
        ),
        sel(
            seq(
                guard(
                    {
                        "or": [
                            {
                                "lt": [
                                    {"ref": "assessment.correctness.confidence"},
                                    LOW_CONFIDENCE_THRESHOLD,
                                ]
                            },
                            {
                                "lt": [
                                    {"ref": "assessment.misconception.confidence"},
                                    LOW_CONFIDENCE_THRESHOLD,
                                ]
                            },
                        ]
                    }
                ),
                act(ask_for_reasoning, ref("question"), ref("student_answer")),
            ),
            seq(
                guard({"eq": [{"ref": "assessment.correctness.choice"}, "correct"]}),
                act(acknowledge_correct),
            ),
            seq(
                guard(
                    {
                        "eq": [
                            {"ref": "assessment.correctness.choice"},
                            "partially_correct",
                        ]
                    }
                ),
                act(ask_next_step, ref("assessment.misconception.choice")),
            ),
            act(explore_error, ref("assessment.misconception.choice")),
        ),
    )
)


if __name__ == "__main__":
    ctx = skill_tutor.run(
        question="Solve 2x + 3 = 11",
        expected_answer="x = 4",
        student_answer="2x = 8, so x = 8",
    )
    print("assessment:", ctx.blackboard.get("assessment"))
