"""Structural verification of the Behavior IR (design §32.1, §45 loader rules).

These are the checks that must pass before a package is trusted, independent of
any trace evidence: every node type known, every ref/signature resolvable, guards
well-formed, loops bounded, ids unique, no forbidden construct. A downloaded
package is executable policy (§22.3) — the loader rejects a malformed one rather
than running it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jdsl.ir.expr import validate_expr
from jdsl.ir.schema import (
    VALID_NODE_TYPES,
    BehaviorIR,
    IRAction,
    IRComposite,
    IRDecorator,
    IRGuard,
    IRGuardCall,
    IRNode,
    IRPredict,
    IRReact,
    IRRepeat,
    Signature,
)

_MAX_REPEAT = 1000  # a compiled package must not ship an effectively unbounded loop


@dataclass
class ValidationReport:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def error(self, msg: str) -> None:
        self.problems.append(msg)

    def __bool__(self) -> bool:
        return self.ok


def validate_ir(ir: BehaviorIR, *, required_capabilities: set[str] | None = None) -> ValidationReport:
    """Validate an IR tree plus its signature table. When `required_capabilities`
    is given, every action tool / react tool must be in it (the manifest contract,
    §22.2)."""
    report = ValidationReport()
    seen_ids: set[str] = set()
    caps: set[str] = set()

    for node in ir.walk():
        _validate_node(node, ir.signatures, report, seen_ids, caps)

    if required_capabilities is not None:
        for cap in sorted(caps):
            if cap not in required_capabilities:
                report.error(f"tool {cap!r} used but not declared in required_capabilities")

    for sig in ir.signatures.values():
        _validate_signature(sig, report)

    return report


def _validate_node(node: IRNode, signatures: dict[str, Signature], report: ValidationReport,
                   seen_ids: set[str], caps: set[str]) -> None:
    if node.type not in VALID_NODE_TYPES:
        report.error(f"forbidden/unknown node type {node.type!r}")
    if node.id is not None:
        if node.id in seen_ids:
            report.error(f"duplicate node id {node.id!r}")
        seen_ids.add(node.id)

    if isinstance(node, IRComposite) and not node.children_:
        report.error(f"{node.type} node {node.id!r} has no children")
    if isinstance(node, IRDecorator) and not isinstance(node, IRRepeat) and node.child is None:
        report.error(f"{node.type} node {node.id!r} has no child")

    if isinstance(node, IRRepeat):
        if node.child is None:
            report.error(f"repeat node {node.id!r} has no child")
        if not isinstance(node.max, int) or node.max < 1 or node.max > _MAX_REPEAT:
            report.error(f"repeat node {node.id!r} has an unbounded/invalid max={node.max!r}")

    if isinstance(node, IRAction):
        if not node.tool:
            report.error(f"action node {node.id!r} names no tool")
        else:
            caps.add(node.tool)
        for name, spec in node.arguments.items():
            if isinstance(spec, dict) and not ({"ref", "const"} & set(spec)):
                report.error(f"action {node.id!r} argument {name!r} is neither a ref nor a const")

    if isinstance(node, IRGuard):
        for p in validate_expr(node.expression):
            report.error(f"guard {node.id!r}: {p}")

    if isinstance(node, IRGuardCall) and not node.predicate:
        report.error(f"guard_call node {node.id!r} names no predicate")

    if isinstance(node, (IRPredict, IRReact)):
        if not node.signature:
            report.error(f"{node.type} node {node.id!r} names no signature")
        elif node.signature not in signatures:
            report.error(f"{node.type} node {node.id!r} references unknown signature {node.signature!r}")
        elif isinstance(node, IRReact):
            caps.update(signatures[node.signature].tools)


def _validate_signature(sig: Signature, report: ValidationReport) -> None:
    if sig.kind not in ("predict", "react"):
        report.error(f"signature {sig.id!r} has unknown kind {sig.kind!r}")
    if sig.output is None:
        report.error(f"signature {sig.id!r} has no output (§18.2: typed output required)")
    elif "type" not in sig.output.schema:
        report.error(f"signature {sig.id!r} output has no type in its schema")
    if sig.kind == "react" and not sig.tools:
        # a react leaf with zero tools should have been a predict (§18.3)
        report.error(f"react signature {sig.id!r} exposes no tools")


__all__ = ["ValidationReport", "validate_ir"]
