"""A JDSL agent that drafts another JDSL behavior package.

The authoring agent can compose only the step palette returned by
``available_steps``. It structurally validates the resulting package and keeps
it in memory until the user approves writing it to ``generated/``.

Run it:  uv run jdsl run examples/author_behavior.py
"""

from __future__ import annotations

import re

from jdsl import act, predict, react, ref, root, seq, store, tool
from jdsl.package import BehaviorPackage, ToolContract, ToolEffects, export_jdsl


STEP_DESCRIPTIONS = {
    "classify": "Classify the request into a short category.",
    "search": "Search an approved knowledge source and store the returned sources.",
    "draft": "Draft an answer, using search results when the search step is included.",
    "review": "Review the drafted answer for accuracy and completeness.",
    "escalate": "Hand the request to a human for follow-up.",
}
_drafts: dict[str, BehaviorPackage] = {}


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:48].strip("-")
    if not slug:
        raise ValueError("name must contain at least one letter or number")
    return slug


@tool
def search_knowledge(query: str) -> list[str]:
    """Placeholder for the host's authorized knowledge-search capability."""
    raise RuntimeError("search_knowledge must be bound to a trusted host implementation")


@tool
def escalate_to_human(request: str) -> str:
    """Placeholder for the host's human-follow-up capability."""
    raise RuntimeError("escalate_to_human must be bound to a trusted host implementation")


TOOL_CONTRACTS = {
    "search_knowledge": ToolContract(
        logical_id="search_knowledge",
        description="Search knowledge sources the caller is authorized to access.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        output_schema={"type": "array", "items": {"type": "string"}},
        effects=ToolEffects(read_only=True),
    ),
    "escalate_to_human": ToolContract(
        logical_id="escalate_to_human",
        description="Create a human follow-up request for the supplied task.",
        input_schema={
            "type": "object",
            "properties": {"request": {"type": "string"}},
            "required": ["request"],
        },
        output_schema={"type": "string"},
        effects=ToolEffects(read_only=False, destructive=False, idempotent=False),
    ),
}


def build_package(name: str, steps: list[str]) -> BehaviorPackage:
    """Compose with the Python DSL, then convert the skill to a package."""
    package_name = _slug(name)
    if not steps:
        raise ValueError("choose at least one workflow step")
    if len(set(steps)) != len(steps):
        raise ValueError("each workflow step may appear only once")
    unknown = sorted(set(steps) - STEP_DESCRIPTIONS.keys())
    if unknown:
        raise ValueError(f"unsupported workflow step(s): {', '.join(unknown)}")
    if "review" in steps and ("draft" not in steps or steps.index("review") < steps.index("draft")):
        raise ValueError("review must appear after draft")
    if "search" in steps and "draft" in steps and steps.index("search") > steps.index("draft"):
        raise ValueError("search must appear before draft")
    if not ({"draft", "escalate"} & set(steps)):
        raise ValueError("include a draft or escalation step to produce an outcome")

    nodes = []
    for step in steps:
        if step == "classify":
            nodes.append(predict(
                "request -> category",
                instructions="Classify the request with a concise category label.",
                id=step,
            ))
        elif step == "search":
            nodes.append(store(act(search_knowledge, ref("request"), id=step), "sources"))
        elif step == "draft":
            draft_inputs = "request, sources -> answer" if "search" in steps[:steps.index(step)] else "request -> answer"
            nodes.append(predict(
                draft_inputs,
                instructions="Answer clearly. Ground factual claims in supplied sources and state uncertainty.",
                id=step,
            ))
        elif step == "review":
            nodes.append(predict(
                "answer -> review",
                instructions="Identify unsupported or incomplete claims. Return 'pass' or a concise correction request.",
                id=step,
            ))
        elif step == "escalate":
            nodes.append(act(escalate_to_human, ref("request"), id=step))

    contracts = {
        tool_name: contract
        for tool_name, contract in TOOL_CONTRACTS.items()
        if (tool_name == "search_knowledge" and "search" in steps)
        or (tool_name == "escalate_to_human" and "escalate" in steps)
    }
    skill = root(
        package_name,
        system="Follow this workflow in order. Use only the declared inputs and capabilities.",
    ).do(seq(*nodes, id="root"))
    return skill.to_package(
        task_family="authored-workflow",
        tool_contracts=contracts,
    )


@tool
def available_steps() -> list[str]:
    """List the safe workflow steps that can be composed into a behavior."""
    return [f"{step}: {description}" for step, description in STEP_DESCRIPTIONS.items()]


@tool
def draft_behavior(name: str, steps: list[str]) -> str:
    """Build and validate a JDSL package draft; do not write it to disk."""
    package = build_package(name, steps)
    _drafts[package.manifest.name] = package
    rendered_steps = " -> ".join(node.id or node.type for node in package.ir.root.children())
    capabilities = ", ".join(package.manifest.required_capabilities) or "none"
    return f"Validated draft '{package.manifest.name}': {rendered_steps}. Required capabilities: {capabilities}."


skill = (
    root(
        "Behavior Author",
        system=(
            "Help the user turn a workflow request into a JDSL behavior package. "
            "First inspect available_steps. Compose only those step ids, in a sensible order. "
            "Ask a brief clarification if the request cannot be represented. "
            "Call draft_behavior to validate a draft, then explain its nodes and required "
            "capabilities. Never claim the package was saved; the user approves saving separately."
        ),
    )
    .model("deepseek-chat")
    .do(react(
        "request -> answer",
        tools=[available_steps, draft_behavior],
        max_steps=6,
    ))
)


def main() -> None:
    _drafts.clear()
    request = input("Describe the workflow to create: ").strip()
    if not request:
        print("No workflow request provided.")
        return

    ctx = skill.run(request=request)
    print("\n", ctx.blackboard.get("answer", "No draft was produced."), sep="")
    if not _drafts:
        return

    package = next(reversed(_drafts.values()))
    print(f"\nStructurally validated draft: {package.manifest.name}.jdsl")
    approval = input("Write this draft under generated/? [y/N] ").strip().lower()
    if approval == "y":
        path = export_jdsl(package, f"generated/{package.manifest.name}.jdsl")
        print(f"Wrote {path}")
    else:
        print("Draft discarded; no package was written.")


if __name__ == "__main__":
    main()