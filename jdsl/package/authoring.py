"""Convert runnable Python-authored trees into portable behavior packages."""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from typing import Any

from jdsl.context import Ref
from jdsl.ir.schema import (
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
    SignatureInput,
    SignatureOutput,
)
from jdsl.ir.validate import validate_ir
from jdsl.package.export import BehaviorPackage
from jdsl.package.manifest import Manifest, ToolContract
from jdsl.tree import (
    Action,
    Check,
    Guard,
    GuardCall,
    Invert,
    Node,
    OneShot,
    Optional,
    Predict,
    React,
    Repeat,
    Root,
    Selector,
    Sequence,
    Timeout,
)


def package_from_root(
    root: Root,
    *,
    tool_contracts: Mapping[str, ToolContract] | None = None,
    task_family: str = "",
    version: str = "0.1.0",
) -> BehaviorPackage:
    """Build a package from a runtime tree without embedding Python callables.

    Contracts are keyed by the exposed host tool name (the function name, or the
    name assigned by ``@tool``). Package IR refers to each contract's logical id.
    """
    if root.child is None:
        raise ValueError(f"Root {root.name!r} has no child to package")

    declared = dict(tool_contracts or {})
    used_names: set[str] = set()
    contracts_by_id: dict[str, ToolContract] = {}
    signatures: dict[str, Signature] = {}

    def capability(tool: Any) -> str:
        host_name, _function = _tool_identity(tool)
        contract = declared.get(host_name)
        if contract is None:
            raise ValueError(
                f"tool {host_name!r} needs an explicit ToolContract in tool_contracts"
            )
        if not isinstance(contract, ToolContract):
            raise TypeError(f"tool_contracts[{host_name!r}] must be a ToolContract")
        if not contract.logical_id:
            raise ValueError(f"tool contract for {host_name!r} needs a logical_id")
        used_names.add(host_name)
        existing = contracts_by_id.get(contract.logical_id)
        if existing is not None and existing.to_dict() != contract.to_dict():
            raise ValueError(f"conflicting contracts use logical id {contract.logical_id!r}")
        contracts_by_id[contract.logical_id] = contract
        return contract.logical_id

    signature_number = 0

    def make_signature(node: Predict | React, contexts: tuple[str, ...], kind: str,
                       tool_ids: list[str] | None = None) -> str:
        nonlocal signature_number
        if len(node.outputs) != 1:
            raise ValueError(
                f"{kind} node {node.effective_id()!r} has multiple outputs; "
                "package signatures currently require one output"
            )
        signature_id = f"{kind}_{signature_number}"
        signature_number += 1
        context_system = "\n\n".join(contexts)
        output = node.outputs[0]
        output_schema = (node.output_schemas or {}).get(output, {"type": "string"}) if isinstance(node, Predict) else {"type": "string"}
        instruction = node.instructions or ""
        signatures[signature_id] = Signature(
            id=signature_id,
            kind=kind,
            inputs={
                name: SignatureInput(source=(node.input_sources or {}).get(name, name))
                for name in node.inputs
            },
            output=SignatureOutput(name=output, schema=output_schema),
            instruction=instruction,
            examples=list(node.examples),
            tools=tool_ids or [],
            context_policy={"system": context_system} if context_system else {},
        )
        return signature_id

    def serializable_value(value: Any, node: Node) -> Any:
        if isinstance(value, Ref):
            return {"ref": value.name}
        if isinstance(value, tuple):
            raise ValueError(f"tuple arguments are not packageable at node {node.effective_id()!r}")
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"argument at node {node.effective_id()!r} is not JSON-serializable"
            ) from error
        return {"const": value}

    def action_arguments(node: Action) -> dict[str, Any]:
        host_name, function = _tool_identity(node.fn)
        try:
            signature = inspect.signature(function)
            bound = signature.bind_partial(*node.args, **node.kwargs)
        except (TypeError, ValueError) as error:
            raise ValueError(f"cannot map arguments for tool {host_name!r}: {error}") from error

        arguments: dict[str, Any] = {}
        for name, parameter in signature.parameters.items():
            if parameter.kind is parameter.VAR_POSITIONAL:
                if bound.arguments.get(name):
                    raise ValueError(f"variadic positional arguments are not packageable for {host_name!r}")
                continue
            if parameter.kind is parameter.VAR_KEYWORD:
                extra = bound.arguments.get(name, {})
                for extra_name, value in extra.items():
                    arguments[extra_name] = serializable_value(value, node)
                continue
            if name not in bound.arguments:
                continue
            if parameter.kind is parameter.POSITIONAL_ONLY:
                raise ValueError(f"positional-only parameter {name!r} is not packageable for {host_name!r}")
            arguments[name] = serializable_value(bound.arguments[name], node)
        return arguments

    def lower(node: Node, path: str, contexts: tuple[str, ...]) -> Any:
        own_context = contexts + ((node.context_system,) if node.context_system else ())
        node_id = node.node_id
        if isinstance(node, Sequence):
            return IRSequence(type="sequence", id=node_id,
                              children_=[lower(child, f"{path}_{index}", own_context)
                                         for index, child in enumerate(node.children)])
        if isinstance(node, Selector):
            return IRSelector(type="selector", id=node_id,
                              children_=[lower(child, f"{path}_{index}", own_context)
                                         for index, child in enumerate(node.children)])
        if isinstance(node, Repeat):
            return IRRepeat(
                type="repeat", id=node_id,
                child=lower(node.child, f"{path}_body", own_context),
                until=lower(node.until, f"{path}_until", own_context) if node.until else None,
                max=node.max,
            )
        if isinstance(node, Optional):
            return IROptional(type="optional", id=node_id,
                              child=lower(node.child, f"{path}_child", own_context))
        if isinstance(node, Invert):
            return IRInvert(type="invert", id=node_id,
                            child=lower(node.child, f"{path}_child", own_context))
        if isinstance(node, Action):
            return IRAction(
                type="action", id=node_id, tool=capability(node.fn),
                arguments=action_arguments(node), store=node.store_as,
            )
        if isinstance(node, Check):
            if isinstance(node.equals, Ref):
                raise ValueError(f"check node {node.effective_id()!r} cannot compare against a Ref")
            return IRCheck(type="check", id=node_id, key=node.key,
                           equals=serializable_value(node.equals, node)["const"])
        if isinstance(node, Guard):
            return IRGuard(type="guard", id=node_id, expression=node.expression)
        if isinstance(node, Predict):
            signature_id = make_signature(node, own_context, "predict")
            return IRPredict(type="predict", id=node_id, signature=signature_id)
        if isinstance(node, React):
            tool_ids = [capability(item) for item in node.tools]
            signature_id = make_signature(node, own_context, "react", tool_ids)
            return IRReact(type="react", id=node_id, signature=signature_id,
                           max_steps=node.max_steps)
        if isinstance(node, GuardCall):
            raise ValueError("guard_call nodes need a separately declared predicate capability and cannot yet be exported")
        if isinstance(node, (Timeout, OneShot)):
            raise ValueError(f"{type(node).__name__} nodes are not representable in Behavior IR")
        raise ValueError(f"node type {type(node).__name__} is not representable in Behavior IR")

    behavior = BehaviorIR(root=lower(root.child, "root", (root.context_system,) if root.context_system else ()),
                          signatures=signatures)
    unused = set(declared) - used_names
    if unused:
        raise ValueError(f"unused tool contract(s): {', '.join(sorted(unused))}")
    capabilities = set(contracts_by_id)
    report = validate_ir(behavior, required_capabilities=capabilities)
    if not report.ok:
        raise ValueError("skill cannot be packaged: " + "; ".join(report.problems))

    return BehaviorPackage(
        manifest=Manifest(
            name=root.name,
            version=version,
            task_family=task_family,
            required_capabilities=sorted(capabilities),
            source={"authoring": "python-dsl"},
            model_id=root.model_id,
        ),
        ir=behavior,
        tools=sorted(contracts_by_id.values(), key=lambda item: item.logical_id),
        readme=(
            f"# {root.name}\n\n"
            "Exported from a Python-authored JDSL skill. The package contains "
            "behavior and capability contracts, not Python tool implementations.\n"
        ),
    )


def _tool_identity(tool: Any) -> tuple[str, Any]:
    function = getattr(tool, "fn", tool)
    name = getattr(tool, "name", None) or getattr(function, "__name__", None)
    if not isinstance(name, str) or not name:
        raise ValueError(f"tool {tool!r} has no stable exposed name")
    return name, function


__all__ = ["package_from_root"]