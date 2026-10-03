import pytest

from jdsl import act, check, react, ref, root, seq, store, tool, timeout
from jdsl.package import ToolContract, ToolEffects, export_jdsl, load_package, load_package_object
from jdsl.tree import React


def test_python_skill_can_run_directly_or_as_a_package(tmp_path):
    @tool
    def echo(message: str) -> str:
        return f"received: {message}"

    contract = ToolContract(
        logical_id="test.echo",
        description="Return the supplied message with a prefix.",
        input_schema={"type": "object", "properties": {"message": {"type": "string"}},
                      "required": ["message"]},
        output_schema={"type": "string"},
        effects=ToolEffects(read_only=True),
    )
    skill = root("Echo", system="Preserve the supplied text.").model("test-model").do(
        seq(
            check("approved", "yes", id="approval"),
            store(act(echo, ref("message"), id="echo"), "response"),
        )
    )

    direct = skill.run(model=object(), message="hello", approved="YES.")
    package = skill.to_package(
        task_family="test",
        tool_contracts={"echo": contract},
    )
    loaded = load_package(export_jdsl(package, tmp_path / "echo"))
    packaged_root = loaded.as_root({"test.echo": echo})
    packaged = packaged_root.run(model=object(), message="hello", approved="YES.")

    assert direct.blackboard["response"] == packaged.blackboard["response"] == "received: hello"
    assert packaged_root.model_id == "test-model"
    assert loaded.tools[0].logical_id == "test.echo"


def test_python_react_preserves_context_tools_and_step_limit():
    @tool
    def search(query: str) -> str:
        return query

    contract = ToolContract(
        logical_id="knowledge.search",
        description="Search approved knowledge sources.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema={"type": "string"},
        effects=ToolEffects(read_only=True),
    )
    skill = root("Research", system="Use approved sources.").model("test-model").do(
        seq(react("question -> answer", tools=[search], max_steps=3, context="Research carefully."),
            context="Scoped policy.")
    )

    package = skill.to_package(tool_contracts={"search": contract})
    loaded = load_package_object(package)
    runtime_root = loaded.as_root({"knowledge.search": search})
    sequence = runtime_root.child
    react_node = sequence.children[0]

    assert isinstance(react_node, React)
    assert react_node.max_steps == 3
    assert react_node.context_system == "Use approved sources.\n\nScoped policy.\n\nResearch carefully."
    assert runtime_root.model_id == "test-model"


def test_python_skill_export_rejects_unsupported_nodes():
    @tool
    def wait_for_service() -> None:
        return None

    skill = root("Unsupported").do(timeout(act(wait_for_service), seconds=2))
    with pytest.raises(ValueError, match="Timeout nodes are not representable"):
        skill.to_package()


def test_python_skill_export_requires_explicit_tool_contracts():
    @tool
    def lookup(query: str) -> str:
        return query

    skill = root("Lookup").do(act(lookup, "term"))
    with pytest.raises(ValueError, match="needs an explicit ToolContract"):
        skill.to_package()