"""A small tutor showing JDSL control flow with a Jev judgment.

Requires ``uv add typesafe-sdk`` and ``TYPESAFE_API_KEY`` in the environment.
Run directly with:

        uv run jdsl run examples/tutor.py -i question="2 + 2" \\
            -i expected_answer="4" -i student_answer="5"

Export a portable behavior package with:

        uv run python examples/tutor.py --export-package

Run the package with:

        uv run jdsl package run examples/tutor.jdsl --tools examples/tutor.py \\
            -i question="2 + 2" -i expected_answer="4" -i student_answer="5"
"""

import argparse

from typesafe_sdk import Choice, TypeSafeClient

from jdsl import act, check, ref, root, sel, seq, store, tool
from jdsl.package import ToolContract, ToolEffects, export_jdsl


@tool
def jev_assess(question: str, expected_answer: str, student_answer: str) -> str:
    """Return a typed judgment about the learner's answer."""
    with TypeSafeClient(model="jev-latest") as client:
        result = client.system_one(
            {
                "question": question,
                "expected_answer": expected_answer,
                "student_answer": student_answer,
            },
            {
                "assessment": Choice(
                    instructions=(
                        "Compare the student's answer with the expected answer. Choose the closest assessment."
                    ),
                    criteria={
                        "correct": "The student's answer is correct.",
                        "partially_correct": "The answer shows some correct understanding but is incomplete.",
                        "incorrect": "The answer is incorrect or shows a misunderstanding.",
                    },
                ),
            },
        )
    return result.answers["assessment"].choice


@tool
def acknowledge_correct() -> None:
    print("Correct. Nice work; explain how you got that answer.")


@tool
def offer_hint() -> None:
    print("You're partway there. Try checking the step where your answer changes.")


@tool
def offer_guidance() -> None:
    print("Not quite. Let's revisit the idea together and try a smaller step.")


skill_tutor = root("Jev tutor").do(
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
            seq(check("assessment", "correct"), act(acknowledge_correct)),
            seq(check("assessment", "partially_correct"), act(offer_hint)),
            act(offer_guidance),
        ),
    )
)

TOOL_CONTRACTS = {
    "jev_assess": ToolContract(
        logical_id="tutor.jev_assess",
        description="Assess a learner's answer using Jev.",
        input_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "expected_answer": {"type": "string"},
                "student_answer": {"type": "string"},
            },
            "required": ["question", "expected_answer", "student_answer"],
        },
        output_schema={
            "type": "string",
            "enum": ["correct", "partially_correct", "incorrect"],
        },
        effects=ToolEffects(read_only=True, idempotent=False),
    ),
    "acknowledge_correct": ToolContract(
        logical_id="tutor.acknowledge_correct",
        description="Respond to a correct answer.",
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema={"type": "null"},
    ),
    "offer_hint": ToolContract(
        logical_id="tutor.offer_hint",
        description="Offer a hint for a partially correct answer.",
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema={"type": "null"},
    ),
    "offer_guidance": ToolContract(
        logical_id="tutor.offer_guidance",
        description="Offer guidance for an incorrect answer.",
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema={"type": "null"},
    ),
}

TOOLS = {
    "tutor.jev_assess": jev_assess,
    "tutor.acknowledge_correct": acknowledge_correct,
    "tutor.offer_hint": offer_hint,
    "tutor.offer_guidance": offer_guidance,
}


def export_tutor_package(path: str = "examples/tutor.jdsl") -> None:
    package = skill_tutor.to_package(
        task_family="tutoring",
        tool_contracts=TOOL_CONTRACTS,
    )
    export_jdsl(package, path)
    print(f"Exported {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-package", action="store_true")
    args = parser.parse_args()

    if args.export_package:
        export_tutor_package()
    else:
        ctx = skill_tutor.run(
            question="What is 2 + 2?",
            expected_answer="4",
            student_answer="5",
        )
        print("Jev assessment:", ctx.blackboard.get("assessment"))
