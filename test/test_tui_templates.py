from jdsl.ir.schema import IRAction, IRReact
from jdsl.ir.validate import validate_ir
from jdsl.tui.templates import TEMPLATES, build_template


def test_example_templates_are_complete_and_valid():
    expected_sources = {
        "greeter.py", "gate.py", "triage.py", "reason.py", "pipeline.py", "refine.py",
        "react.py", "trip.py", "shop.py", "db.py", "wiki.py",
    }
    assert {template.source for template in TEMPLATES} == expected_sources

    for template in TEMPLATES:
        ir, contracts = build_template(template.id)
        declared = {contract.logical_id for contract in contracts}
        used = {node.tool for node in ir.walk() if isinstance(node, IRAction)}
        for node in ir.walk():
            if isinstance(node, IRReact):
                used.update(ir.signatures[node.signature].tools)
        report = validate_ir(ir, required_capabilities=declared)
        assert report.ok, f"{template.id}: {report.problems}"
        assert used == declared, f"{template.id}: missing or unused contracts"


def test_template_builds_are_independent():
    first, _ = build_template("triage")
    second, _ = build_template("triage")
    first.root.id = "changed"
    assert second.root.id == "root"