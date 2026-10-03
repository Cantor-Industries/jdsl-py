import pytest

from jdsl.ir.validate import validate_ir
from jdsl.package import export_jdsl, load_package
from examples.author_behavior import build_package


def test_authoring_example_builds_valid_package_with_bound_capabilities(tmp_path):
    package = build_package("Support Reply", ["classify", "search", "draft", "review"])

    assert package.manifest.name == "support-reply"
    assert package.manifest.required_capabilities == ["search_knowledge"]
    assert [node.id for node in package.ir.root.children()] == ["classify", "search", "draft", "review"]
    assert validate_ir(package.ir, required_capabilities=set(package.manifest.required_capabilities)).ok

    loaded = load_package(export_jdsl(package, tmp_path / "support-reply"))
    assert loaded.ir.to_dict() == package.ir.to_dict()
    assert loaded.manifest.required_capabilities == ["search_knowledge"]


@pytest.mark.parametrize(
    "steps",
    [
        [],
        ["draft", "review", "search"],
        ["review", "draft"],
        ["unknown_step", "draft"],
        ["draft", "draft"],
        ["classify"],
    ],
)
def test_authoring_example_rejects_invalid_step_plans(steps):
    with pytest.raises(ValueError):
        build_package("invalid", steps)