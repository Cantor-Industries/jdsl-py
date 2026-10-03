"""A JDSL agent that authors and reviews another JDSL behavior package.

Run it:  uv run jdsl run examples/author_behavior.py
"""

from __future__ import annotations

import json
from typing import Any

from jdsl import check, predict, react, repeat, root, sel, seq, tool
from jdsl.ir.schema import IRAction, IRNode, IRPredict, IRReact
from jdsl.package import (
    BehaviorPackage,
    ToolContract,
    ToolEffects,
    behavior_ir_authoring_guide,
    export_jdsl,
)
from jdsl.package import package_from_proposal as _package_from_proposal


_drafts: dict[str, BehaviorPackage] = {}

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


@tool
def jdsl_node_reference() -> str:
    """Describe the supported JDSL IR grammar and its node semantics."""
    return behavior_ir_authoring_guide()


@tool
def available_capabilities() -> str:
    """Return the host capability contracts the generated tree may use."""
    return json.dumps(
        [contract.to_dict() for contract in TOOL_CONTRACTS.values()],
        sort_keys=True,
        indent=2,
    )


def package_from_proposal(name: str, proposal_json: str) -> BehaviorPackage:
    """Apply this example's capability policy to a proposed Behavior IR tree."""
    return _package_from_proposal(
        name,
        proposal_json,
        tool_contracts=TOOL_CONTRACTS,
        task_family="authored-workflow",
        model_id="deepseek-chat",
    )


def _render_tree(node: IRNode, depth: int = 0) -> list[str]:
    detail = f" {node.id}" if node.id else ""
    if isinstance(node, IRAction):
        detail += f" [{node.tool}]"
    elif isinstance(node, (IRPredict, IRReact)):
        detail += f" [{node.signature}]"
    lines = [f"{'  ' * depth}{node.type}{detail}"]
    for child in node.children():
        lines.extend(_render_tree(child, depth + 1))
    return lines


@tool
def draft_behavior(name: str, proposal_json: str) -> str:
    """Validate a nested IR proposal and hold it for explicit user approval."""
    package = package_from_proposal(name, proposal_json)
    _drafts[package.manifest.name] = package
    capabilities = ", ".join(package.manifest.required_capabilities) or "none"
    tree = "\n".join(_render_tree(package.ir.root))
    return f"Validated draft '{package.manifest.name}'. Capabilities: {capabilities}.\nTree:\n{tree}"


def _authoring_loop():
    return repeat(
        seq(
            react(
                "request, feedback -> answer",
                tools=[jdsl_node_reference, available_capabilities, draft_behavior],
                instructions=(
                    "Author a nested JDSL tree from the supplied grammar and capability catalog. "
                    "Call draft_behavior and repair validation errors. If feedback contains a "
                    "review request, revise the tree. Return its package name, tree, and "
                    "capabilities; do not claim the package was saved."
                ),
                max_steps=8,
                id="author_tree",
            ),
            predict(
                "request, answer -> feedback",
                instructions=(
                    "Review whether the proposed tree addresses the request and uses sensible "
                    "control flow. Return exactly 'approved' only when it does; otherwise give "
                    "one actionable revision request. A validated package is not yet saved."
                ),
                id="review_tree",
            ),
            id="author_and_review",
        ),
        until=check("feedback", "approved", id="review_approved"),
        max=2,
        id="bounded_review_loop",
    )


skill = root(
    "Behavior Author",
    system=(
        "Help users author JDSL behavior trees. Classify each request as author or explain. "
        "For author requests, use the documented IR grammar, validate the proposal, and review "
        "it. For explain requests, answer using the node reference. Never save a package without "
        "explicit user approval."
    ),
).model("deepseek-chat").do(
    seq(
        predict(
            "request -> intent",
            instructions="Return exactly 'author' for tree-creation requests, otherwise 'explain'.",
            id="classify_request",
        ),
        sel(
            seq(
                check("intent", "author", id="is_author_request"),
                _authoring_loop(),
                id="author_route",
            ),
            seq(
                check("intent", "explain", id="is_explanation_request"),
                react(
                    "request -> answer",
                    tools=[jdsl_node_reference],
                    instructions="Answer the JDSL question using the node reference; do not author a package.",
                    max_steps=3,
                    id="explain_jdsl",
                ),
                id="explain_route",
            ),
            predict(
                "request -> answer",
                instructions="Explain that this assistant handles JDSL tree authoring or JDSL questions; ask the user to reframe other requests.",
                id="unsupported_request",
            ),
            id="route_request",
        ),
        id="authoring_workflow",
    ),
)


def main() -> None:
    _drafts.clear()
    request = input("Describe a behavior tree or ask about JDSL: ").strip()
    if not request:
        print("No request provided.")
        return

    context = skill.run(
        request=request,
        feedback="No draft exists yet. Create one from the request.",
    )
    print("\n", context.blackboard.get("answer", "No answer produced."), sep="")
    if context.blackboard.get("intent") != "author":
        return
    if context.blackboard.get("feedback") != "approved":
        print("\nReview did not approve the draft; no package was written.")
        return
    if not _drafts:
        print("\nNo valid package draft was produced.")
        return

    package = next(reversed(_drafts.values()))
    print(f"\nValidated draft: {package.manifest.name}.jdsl")
    approval = input("Write this draft under generated/? [y/N] ").strip().lower()
    if approval == "y":
        path = export_jdsl(package, f"generated/{package.manifest.name}.jdsl")
        print(f"Wrote {path}")
    else:
        print("Draft discarded; no package was written.")


if __name__ == "__main__":
    main()