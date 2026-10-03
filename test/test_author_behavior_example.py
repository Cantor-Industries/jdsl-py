import json

import pytest

from jdsl import ModelTurn, ToolCall
from jdsl.ir.validate import validate_ir
from jdsl.package import export_jdsl, load_package
from jdsl.ir.schema import IRReact
from jdsl.tree import Check, Predict, React, Repeat, Selector, Sequence
from examples import author_behavior
from examples.author_behavior import available_capabilities, jdsl_node_reference, package_from_proposal


def _proposal():
    return {
        "behavior": {
            "format": "jdsl.behavior.v1",
            "root": {
                "type": "sequence",
                "id": "root",
                "children": [
                    {"type": "predict", "id": "classify", "signature": "classify_request"},
                    {
                        "type": "selector",
                        "id": "route",
                        "children": [
                            {
                                "type": "sequence",
                                "id": "research_route",
                                "children": [
                                    {"type": "check", "id": "is_research", "key": "category", "equals": "research"},
                                    {
                                        "type": "action",
                                        "id": "search",
                                        "tool": "search_knowledge",
                                        "arguments": {"query": {"ref": "request"}},
                                        "store": "sources",
                                    },
                                    {"type": "predict", "id": "answer", "signature": "draft_answer"},
                                ],
                            },
                            {
                                "type": "action",
                                "id": "escalate",
                                "tool": "escalate_to_human",
                                "arguments": {"request": {"ref": "request"}},
                            },
                        ],
                    },
                ],
            },
        },
        "signatures": {
            "classify_request": {
                "id": "classify_request",
                "kind": "predict",
                "inputs": {"request": {"source": "request", "schema": {"type": "string"}}},
                "output": {"name": "category", "schema": {"type": "string", "enum": ["research", "other"]}},
                "instruction": "Classify the request.",
            },
            "draft_answer": {
                "id": "draft_answer",
                "kind": "predict",
                "inputs": {
                    "request": {"source": "request", "schema": {"type": "string"}},
                    "sources": {"source": "sources", "schema": {"type": "array", "items": {"type": "string"}}},
                },
                "output": {"name": "answer", "schema": {"type": "string"}},
                "instruction": "Answer using the supplied sources.",
            },
        },
    }


def test_authoring_agent_builds_and_exports_a_nested_tree(tmp_path):
    import json

    package = package_from_proposal("Support Reply", json.dumps(_proposal()))

    assert package.manifest.name == "support-reply"
    assert package.manifest.required_capabilities == ["escalate_to_human", "search_knowledge"]
    assert [node.type for node in package.ir.root.children()] == ["predict", "selector"]
    assert validate_ir(package.ir, required_capabilities=set(package.manifest.required_capabilities)).ok

    loaded = load_package(export_jdsl(package, tmp_path / "support-reply"))
    assert loaded.ir.to_dict() == package.ir.to_dict()
    assert loaded.manifest.required_capabilities == ["escalate_to_human", "search_knowledge"]


def test_authoring_agent_executes_tool_proposal_loop(fake_model):
    author_behavior._drafts.clear()
    model = fake_model("author", "approved", turns=[
        ModelTurn(tool_calls=[ToolCall(id="1", name="jdsl_node_reference", arguments={})]),
        ModelTurn(tool_calls=[ToolCall(id="2", name="available_capabilities", arguments={})]),
        ModelTurn(tool_calls=[ToolCall(id="3", name="draft_behavior", arguments={
            "name": "Support Reply",
            "proposal_json": json.dumps(_proposal()),
        })]),
        ModelTurn(text="I drafted and validated a support workflow."),
    ])

    context = author_behavior.skill.run(
        model=model,
        request="Answer policy questions and escalate others.",
        feedback="No draft exists yet. Create one from the request.",
    )

    assert context.blackboard["answer"] == "I drafted and validated a support workflow."
    assert "support-reply" in author_behavior._drafts
    assert len(model.converse_calls) == 4
    assert any(
        message.get("role") == "tool" and "selector" in message.get("content", "")
        for message in model.converse_calls[2]["messages"]
    )


def test_authoring_agent_is_orchestrated_by_multiple_jdsl_nodes():
    tree = author_behavior.skill.child
    assert isinstance(tree, Sequence)
    classify, route = tree.children
    assert isinstance(classify, Predict)
    assert isinstance(route, Selector)

    author_route = route.children[0]
    assert isinstance(author_route, Sequence)
    assert isinstance(author_route.children[0], Check)
    review_loop = author_route.children[1]
    assert isinstance(review_loop, Repeat)
    assert isinstance(review_loop.child.children[0], React)
    assert isinstance(review_loop.child.children[1], Predict)
    assert isinstance(route.children[1].children[0], Check)


def test_authoring_agent_exposes_node_grammar_and_capability_contracts():
    reference = jdsl_node_reference()
    assert '"type":"selector"' in reference
    assert "first success" in reference
    assert '"type":"repeat"' in reference

    capabilities = available_capabilities()
    assert "search_knowledge" in capabilities
    assert "input_schema" in capabilities


def test_authoring_agent_supports_repeat_and_react_nodes(tmp_path):
    import json

    proposal = {
        "behavior": {
            "format": "jdsl.behavior.v1",
            "root": {
                "type": "sequence",
                "id": "root",
                "children": [{
                    "type": "repeat",
                    "id": "retry",
                    "max": 2,
                    "child": {"type": "react", "id": "research", "signature": "research", "max_steps": 4},
                    "until": {"type": "check", "id": "done", "key": "answer", "equals": "done"},
                }],
            },
        },
        "signatures": {
            "research": {
                "id": "research",
                "kind": "react",
                "inputs": {"question": {"source": "request", "schema": {"type": "string"}}},
                "output": {"name": "answer", "schema": {"type": "string"}},
                "instruction": "Research the question using tools.",
                "tools": ["search_knowledge"],
            },
        },
    }
    package = package_from_proposal("Research", json.dumps(proposal))
    loaded = load_package(export_jdsl(package, tmp_path / "research"))
    react_node = next(node for node in loaded.ir.walk() if isinstance(node, IRReact))

    assert react_node.max_steps == 4
    assert loaded.manifest.required_capabilities == ["search_knowledge"]


def test_authoring_agent_rejects_unknown_capabilities():
    import json

    proposal = _proposal()
    proposal["behavior"]["root"]["children"][1]["children"][0]["children"][1]["tool"] = "send_payment"
    with pytest.raises(ValueError):
        package_from_proposal("invalid", json.dumps(proposal))


def test_authoring_agent_rejects_unknown_or_malformed_nodes():
    import json

    proposal = _proposal()
    proposal["behavior"]["root"]["children"][0]["type"] = "python"
    with pytest.raises(ValueError, match="unsupported node type"):
        package_from_proposal("invalid", json.dumps(proposal))

    proposal = _proposal()
    proposal["behavior"]["root"]["children"][1]["children"][0]["children"][1]["arguments"]["query"] = {
        "ref": "request", "const": "untrusted"
    }
    with pytest.raises(ValueError, match="exactly one of 'ref' or 'const'"):
        package_from_proposal("invalid", json.dumps(proposal))


def test_authoring_agent_rejects_ir_validation_errors():
    import json

    proposal = _proposal()
    proposal["behavior"]["root"]["children"][0]["signature"] = "missing_signature"
    with pytest.raises(ValueError, match="missing signature"):
        package_from_proposal("invalid", json.dumps(proposal))

    proposal = _proposal()
    answer_node = proposal["behavior"]["root"]["children"][1]["children"][0]["children"][2]
    answer_node["type"] = "react"
    answer_node["signature"] = "classify_request"
    with pytest.raises(ValueError, match="is react but signature"):
        package_from_proposal("invalid", json.dumps(proposal))

    proposal = _proposal()
    proposal["behavior"]["root"]["children"][1]["children"][0]["children"][1]["arguments"]["query"]["ref"] = "missing_input"
    with pytest.raises(ValueError, match="reads 'missing_input' before it is available"):
        package_from_proposal("invalid", json.dumps(proposal))