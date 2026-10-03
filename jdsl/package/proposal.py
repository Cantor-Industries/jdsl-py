"""Validate model-authored Behavior IR and turn it into a package draft."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from jdsl.ir.schema import (
    BEHAVIOR_FORMAT,
    BehaviorIR,
    IRAction,
    IRCheck,
    IRGuard,
    IRInvert,
    IROptional,
    IRPredict,
    IRReact,
    IRRepeat,
    IRSelector,
    IRSequence,
    Signature,
)
from jdsl.ir.validate import validate_ir
from jdsl.package.export import BehaviorPackage
from jdsl.package.manifest import Manifest, ToolContract

_NODE_FIELDS = {
    "sequence": {"type", "id", "children"},
    "selector": {"type", "id", "children"},
    "optional": {"type", "id", "child"},
    "invert": {"type", "id", "child"},
    "repeat": {"type", "id", "child", "until", "max"},
    "action": {"type", "id", "tool", "arguments", "store"},
    "guard": {"type", "id", "expression"},
    "check": {"type", "id", "key", "equals"},
    "predict": {"type", "id", "signature"},
    "react": {"type", "id", "signature", "max_steps"},
}
_REQUIRED_NODE_FIELDS = {
    "sequence": {"children"},
    "selector": {"children"},
    "optional": {"child"},
    "invert": {"child"},
    "repeat": {"child"},
    "action": {"tool"},
    "guard": {"expression"},
    "check": {"key", "equals"},
    "predict": {"signature"},
    "react": {"signature"},
}
_SIGNATURE_FIELDS = {
    "format", "id", "kind", "inputs", "output", "instruction", "examples",
    "tools", "context_policy", "validator",
}


def behavior_ir_authoring_guide() -> str:
    """A compact authoring contract for an LLM proposing Behavior IR JSON."""
    return f"""JDSL behavior authoring format: {BEHAVIOR_FORMAT}

Return one JSON object with exactly two keys:
- behavior: an object with format={BEHAVIOR_FORMAT!r} and root=<node>
- signatures: an object keyed by signature id

Node forms and semantics:
- sequence: {{"type":"sequence","id":"unique-id","children":[node,...]}}; run in order, stop on first failure.
- selector: {{"type":"selector","id":"unique-id","children":[node,...]}}; try in order, stop on first success.
- optional: {{"type":"optional","id":"unique-id","child":node}}; always succeeds after running its child.
- invert: {{"type":"invert","id":"unique-id","child":node}}; reverses the child's success/failure.
- repeat: {{"type":"repeat","id":"unique-id","child":node,"max":3,"until":optional-node}}; bounded loop, stops when until succeeds.
- action: {{"type":"action","id":"unique-id","tool":"capability-id","arguments":{{"arg":{{"ref":"input"}}}},"store":"optional-key"}}; calls a host capability.
- guard: {{"type":"guard","id":"unique-id","expression":{{"eq":[{{"ref":"key"}},"value"]}}}}; expression operators: exists, eq, neq, lt, lte, gt, gte, in, and, or, not.
- check: {{"type":"check","id":"unique-id","key":"category","equals":"research"}}; compares one blackboard key to a JSON value.
- predict: {{"type":"predict","id":"unique-id","signature":"signature-id"}}; one model call.
- react: {{"type":"react","id":"unique-id","signature":"signature-id","max_steps":6}}; bounded model/tool loop.

Signatures use fields id, kind (predict or react), inputs, output, instruction, examples, tools, context_policy, and validator. Each input is {{"source":"blackboard-key","schema":{{"type":"string"}}}}. Each signature has exactly one output, e.g. {{"name":"answer","schema":{{"type":"string"}}}}. A react signature lists capability ids in tools. Put extra system guidance in context_policy={{"system":"..."}}.

Rules: every node needs a unique non-empty id; composites need at least one child; refs must be produced earlier or supplied as inputs; repeat and react limits must be bounded; action arguments must match the selected capability's required/property names; action/react tools must be chosen from the supplied capability catalog; never emit guard_call or executable code. For action arguments, use exactly one of {{"ref":"path"}} or {{"const":json-value}}.

Minimal example shape:
{{"behavior":{{"format":"{BEHAVIOR_FORMAT}","root":{{"type":"sequence","id":"root","children":[{{"type":"predict","id":"answer","signature":"answer_sig"}}]}}}}}},"signatures":{{"answer_sig":{{"id":"answer_sig","kind":"predict","inputs":{{"request":{{"source":"request","schema":{{"type":"string"}}}}}},"output":{{"name":"answer","schema":{{"type":"string"}}}},"instruction":"Answer the request clearly."}}}}}}
"""


def package_from_proposal(
    name: str,
    proposal_json: str,
    *,
    tool_contracts: Mapping[str, ToolContract],
    task_family: str = "",
    model_id: str | None = None,
    initial_inputs: set[str] | None = None,
) -> BehaviorPackage:
    """Parse model-proposed IR, bind only listed contracts, and validate it."""
    package_name = _slug(name)
    try:
        proposal = json.loads(proposal_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"proposal_json is not valid JSON: {error.msg}") from error
    if not isinstance(proposal, dict) or set(proposal) != {"behavior", "signatures"}:
        raise ValueError("proposal must contain exactly 'behavior' and 'signatures'")

    behavior = proposal["behavior"]
    if not isinstance(behavior, dict) or behavior.get("format") != BEHAVIOR_FORMAT:
        raise ValueError(f"behavior.format must be {BEHAVIOR_FORMAT!r}")
    if set(behavior) != {"format", "root"}:
        raise ValueError("behavior must contain exactly 'format' and 'root'")
    _validate_node_shape(behavior["root"])

    signature_data = proposal["signatures"]
    if not isinstance(signature_data, dict):
        raise ValueError("signatures must be an object keyed by signature id")
    signatures: dict[str, Signature] = {}
    for signature_id, signature in signature_data.items():
        if not isinstance(signature_id, str) or not isinstance(signature, dict):
            raise ValueError("each signature must be an object keyed by its string id")
        extra = set(signature) - _SIGNATURE_FIELDS
        if extra:
            raise ValueError(f"signature {signature_id!r} has unknown fields: {', '.join(sorted(extra))}")
        missing = {"id", "kind", "inputs", "output"} - set(signature)
        if missing:
            raise ValueError(f"signature {signature_id!r} is missing fields: {', '.join(sorted(missing))}")
        if signature["id"] != signature_id:
            raise ValueError(f"signature key {signature_id!r} does not match its id")
        if signature["kind"] not in {"predict", "react"}:
            raise ValueError(f"signature {signature_id!r} kind must be 'predict' or 'react'")
        inputs = signature["inputs"]
        if not isinstance(inputs, dict):
            raise ValueError(f"signature {signature_id!r} inputs must be an object")
        for alias, item in inputs.items():
            if not isinstance(alias, str) or not alias or not isinstance(item, dict):
                raise ValueError(f"signature {signature_id!r} has an invalid input field")
            source = item.get("source", alias)
            if not isinstance(source, str) or not source:
                raise ValueError(f"signature {signature_id!r} input {alias!r} needs a source path")
            if not isinstance(item.get("schema", {"type": "string"}), dict):
                raise ValueError(f"signature {signature_id!r} input {alias!r} schema must be an object")
        output = signature["output"]
        if not isinstance(output, dict) or not isinstance(output.get("name"), str) or not output["name"]:
            raise ValueError(f"signature {signature_id!r} needs one named output")
        if not isinstance(output.get("schema", {"type": "string"}), dict):
            raise ValueError(f"signature {signature_id!r} output schema must be an object")
        tools = signature.get("tools", [])
        if not isinstance(tools, list) or any(not isinstance(item, str) for item in tools):
            raise ValueError(f"signature {signature_id!r} tools must be a list of capability ids")
        if not isinstance(signature.get("context_policy", {}), dict):
            raise ValueError(f"signature {signature_id!r} context_policy must be an object")
        signatures[signature_id] = Signature.from_dict(signature)

    ir = BehaviorIR.from_dict(behavior, signatures=signatures)
    used_signature_ids = {
        node.signature for node in ir.walk() if isinstance(node, (IRPredict, IRReact))
    }
    missing_signatures = used_signature_ids - set(signatures)
    if missing_signatures:
        raise ValueError(f"missing signature(s): {', '.join(sorted(missing_signatures))}")
    for node in ir.walk():
        if isinstance(node, (IRPredict, IRReact)):
            expected_kind = "react" if isinstance(node, IRReact) else "predict"
            if signatures[node.signature].kind != expected_kind:
                raise ValueError(
                    f"node {node.id!r} is {expected_kind} but signature {node.signature!r} "
                    f"is {signatures[node.signature].kind}"
                )
    unused_signatures = set(signatures) - used_signature_ids
    if unused_signatures:
        raise ValueError(f"unused signature(s): {', '.join(sorted(unused_signatures))}")

    used_capabilities = {node.tool for node in ir.walk() if isinstance(node, IRAction)}
    for signature in signatures.values():
        if signature.kind == "react":
            used_capabilities.update(signature.tools)
    catalog = dict(tool_contracts)
    unknown_capabilities = used_capabilities - catalog.keys()
    if unknown_capabilities:
        raise ValueError(f"unknown capability(s): {', '.join(sorted(unknown_capabilities))}")
    for capability_id, contract in catalog.items():
        if contract.logical_id != capability_id:
            raise ValueError(f"tool contract key {capability_id!r} does not match its logical id")
    for node in ir.walk():
        if isinstance(node, IRAction):
            _validate_action_arguments(node, catalog[node.tool])

    report = validate_ir(ir, required_capabilities=used_capabilities)
    if not report.ok:
        raise ValueError("draft failed JDSL validation: " + "; ".join(report.problems))
    _validate_dataflow(ir, set(initial_inputs or {"request"}))

    contracts = [catalog[item] for item in sorted(used_capabilities)]
    return BehaviorPackage(
        manifest=Manifest(
            name=package_name,
            task_family=task_family,
            required_capabilities=sorted(used_capabilities),
            source={"authoring": "model-proposal"},
            model_id=model_id,
        ),
        ir=ir,
        tools=contracts,
        readme=(
            f"# {package_name}\n\n"
            "Drafted from a model-authored Behavior IR proposal. The package contains "
            "validated behavior and capability contracts, not Python tool implementations.\n"
        ),
    )


def _validate_node_shape(data: Any, path: str = "root") -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    node_type = data.get("type")
    if node_type not in _NODE_FIELDS:
        raise ValueError(f"unsupported node type at {path}: {node_type!r}")
    extra = set(data) - _NODE_FIELDS[node_type]
    missing = _REQUIRED_NODE_FIELDS[node_type] - set(data)
    if extra or missing:
        details = []
        if extra:
            details.append(f"unknown field(s): {', '.join(sorted(extra))}")
        if missing:
            details.append(f"missing field(s): {', '.join(sorted(missing))}")
        raise ValueError(f"invalid {node_type} node at {path}: {'; '.join(details)}")
    if not isinstance(data.get("id"), str) or not data["id"].strip():
        raise ValueError(f"{path}.id must be a non-empty string")
    if node_type == "action" and (not isinstance(data["tool"], str) or not data["tool"]):
        raise ValueError(f"{path}.tool must be a non-empty capability id")
    if node_type == "check" and (not isinstance(data["key"], str) or not data["key"]):
        raise ValueError(f"{path}.key must be a non-empty string")
    if node_type in {"predict", "react"} and (
        not isinstance(data["signature"], str) or not data["signature"]
    ):
        raise ValueError(f"{path}.signature must be a non-empty string")

    if node_type in {"sequence", "selector"}:
        children = data["children"]
        if not isinstance(children, list):
            raise ValueError(f"{path}.children must be a list")
        for index, child in enumerate(children):
            _validate_node_shape(child, f"{path}.children[{index}]")
    elif node_type in {"optional", "invert", "repeat"}:
        _validate_node_shape(data["child"], f"{path}.child")
        if data.get("until") is not None:
            _validate_node_shape(data["until"], f"{path}.until")
    elif node_type == "action":
        arguments = data.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError(f"{path}.arguments must be an object")
        for name, spec in arguments.items():
            if not isinstance(spec, dict) or len(spec) != 1 or not ("ref" in spec or "const" in spec):
                raise ValueError(f"{path}.arguments[{name!r}] must contain exactly one of 'ref' or 'const'")
            if "ref" in spec and not isinstance(spec["ref"], str):
                raise ValueError(f"{path}.arguments[{name!r}].ref must be a string")


def _validate_action_arguments(node: IRAction, contract: ToolContract) -> None:
    properties = contract.input_schema.get("properties", {})
    required = set(contract.input_schema.get("required", []))
    actual = set(node.arguments)
    missing = required - actual
    unknown = actual - set(properties) if properties else set()
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing arguments: {', '.join(sorted(missing))}")
        if unknown:
            details.append(f"unknown arguments: {', '.join(sorted(unknown))}")
        raise ValueError(f"action {node.id!r} for {node.tool!r}: {'; '.join(details)}")


def _references(value: Any):
    if isinstance(value, dict):
        if set(value) == {"ref"} and isinstance(value["ref"], str):
            yield value["ref"]
        elif set(value) == {"exists"} and isinstance(value["exists"], str):
            yield value["exists"]
        else:
            for child in value.values():
                yield from _references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _references(child)


def _validate_dataflow(ir: BehaviorIR, initial: set[str]) -> None:
    def require(path: str, node_id: str | None, available: set[str]) -> None:
        root_name = path.removeprefix("blackboard.").split(".", 1)[0].split("[", 1)[0]
        if root_name not in available:
            raise ValueError(f"node {node_id!r} reads {path!r} before it is available")

    def visit(node, available: set[str]) -> set[str]:
        if isinstance(node, IRSequence):
            current = set(available)
            for child in node.children_:
                current = visit(child, current)
            return current
        if isinstance(node, IRSelector):
            branches = [visit(child, set(available)) for child in node.children_]
            return set.intersection(*branches) if branches else set(available)
        if isinstance(node, IRRepeat):
            after_body = visit(node.child, set(available))
            if node.until is not None:
                visit(node.until, after_body)
            return set(available)
        if isinstance(node, (IROptional, IRInvert)):
            visit(node.child, set(available))
            return set(available)
        if isinstance(node, IRAction):
            for path in _references(node.arguments):
                require(path, node.id, available)
            current = set(available)
            if node.store:
                current.add(node.store)
            return current
        if isinstance(node, IRCheck):
            require(node.key, node.id, available)
            return set(available)
        if isinstance(node, IRGuard):
            for path in _references(node.expression):
                require(path, node.id, available)
            return set(available)
        if isinstance(node, (IRPredict, IRReact)):
            signature = ir.signatures[node.signature]
            for item in signature.inputs.values():
                require(item.source, node.id, available)
            current = set(available)
            if signature.output:
                current.add(signature.output.name)
            return current
        return set(available)

    visit(ir.root, set(initial))


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:48].strip("-")
    if not slug:
        raise ValueError("name must contain at least one letter or number")
    return slug


__all__ = ["behavior_ir_authoring_guide", "package_from_proposal"]