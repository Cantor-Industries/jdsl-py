"""Lower the Behavior IR into the existing runtime `Node` classes (design §35 PR11
"Lower IR into existing Node classes").

The IR is model-neutral and refers to *logical* capabilities, predicate ids, and
signature ids. Lowering binds those to concrete runtime objects supplied by the
host (§12.1 runtime binding): a missing capability makes lowering fail before any
execution, never silently at run time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jdsl.context import Ref
from jdsl.ir.schema import (
    BehaviorIR,
    IRAction,
    IRComposite,
    IRGuard,
    IRGuardCall,
    IRInvert,
    IRNode,
    IROptional,
    IRPredict,
    IRReact,
    IRRepeat,
    IRSelector,
    IRSequence,
    Signature,
)
from jdsl.tree import (
    Action,
    Guard,
    GuardCall,
    Invert,
    Node,
    Optional,
    Predict,
    React,
    Repeat,
    Selector,
    Sequence,
)


class BindingError(ValueError):
    """A required capability / predicate / signature was not supplied at load."""


@dataclass
class RuntimeBindings:
    """What the host provides to run a package (§12.1, §40). Tools are keyed by
    logical capability id; predicates by guard-call id; signatures by id."""
    tools: dict[str, Any] = field(default_factory=dict)
    predicates: dict[str, Any] = field(default_factory=dict)
    signatures: dict[str, Signature] = field(default_factory=dict)

    def tool(self, logical_id: str) -> Any:
        if logical_id not in self.tools:
            raise BindingError(f"no tool bound for capability {logical_id!r}")
        return self.tools[logical_id]

    def predicate(self, pid: str) -> Any:
        if pid not in self.predicates:
            raise BindingError(f"no predicate bound for {pid!r}")
        return self.predicates[pid]

    def signature(self, sid: str) -> Signature:
        if sid not in self.signatures:
            raise BindingError(f"no signature named {sid!r}")
        return self.signatures[sid]


def lower(ir: BehaviorIR, bindings: RuntimeBindings) -> Node:
    """Lower a whole behavior IR to a runnable tree. Signatures come from
    `bindings` if present, else from the IR's own signature table."""
    merged = RuntimeBindings(tools=bindings.tools, predicates=bindings.predicates,
                             signatures={**ir.signatures, **bindings.signatures})
    return lower_node(ir.root, merged)


def lower_node(node: IRNode, b: RuntimeBindings) -> Node:
    out = _lower_dispatch(node, b)
    if node.id is not None:
        out.node_id = node.id
    return out


def _lower_dispatch(node: IRNode, b: RuntimeBindings) -> Node:
    if isinstance(node, IRSequence):
        return Sequence(children=[lower_node(c, b) for c in node.children_])
    if isinstance(node, IRSelector):
        return Selector(children=[lower_node(c, b) for c in node.children_])
    if isinstance(node, IROptional):
        return Optional(child=lower_node(node.child, b))
    if isinstance(node, IRInvert):
        return Invert(child=lower_node(node.child, b))
    if isinstance(node, IRRepeat):
        return Repeat(child=lower_node(node.child, b),
                      until=lower_node(node.until, b) if node.until else None, max=node.max)
    if isinstance(node, IRAction):
        act = Action(fn=b.tool(node.tool), kwargs=_lower_args(node.arguments), store_as=node.store)
        return act
    if isinstance(node, IRGuard):
        return Guard(expression=node.expression)
    if isinstance(node, IRGuardCall):
        return GuardCall(predicate=b.predicate(node.predicate), predicate_id=node.predicate,
                         arguments=_lower_args(node.arguments))
    if isinstance(node, IRPredict):
        return _lower_predict(b.signature(node.signature))
    if isinstance(node, IRReact):
        return _lower_react(b.signature(node.signature), b)
    if isinstance(node, IRComposite):  # unknown composite -> sequence
        return Sequence(children=[lower_node(c, b) for c in node.children_])
    raise BindingError(f"cannot lower IR node of type {node.type!r}")


def _lower_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """Turn IR argument specs ({ref}/{const}) into runtime kwargs (Ref/literal)."""
    out: dict[str, Any] = {}
    for name, spec in arguments.items():
        if isinstance(spec, dict) and "ref" in spec:
            out[name] = Ref(spec["ref"])
        elif isinstance(spec, dict) and "const" in spec:
            out[name] = spec["const"]
        else:
            out[name] = spec
    return out


def _lower_predict(sig: Signature) -> Predict:
    inputs = tuple(inp.field_name() for inp in sig.inputs.values())
    outputs = (sig.output.name,) if sig.output else ()
    schemas = {sig.output.name: sig.output.schema} if sig.output else None
    return Predict(inputs=inputs, outputs=outputs, instructions=sig.instruction or None,
                   output_schemas=schemas, signature_id=sig.id)


def _lower_react(sig: Signature, b: RuntimeBindings) -> React:
    inputs = tuple(inp.field_name() for inp in sig.inputs.values())
    outputs = (sig.output.name,) if sig.output else ("answer",)
    tools = [b.tool(t) for t in sig.tools]
    return React(inputs=inputs, outputs=outputs, tools=tools, instructions=sig.instruction or None)


__all__ = ["RuntimeBindings", "BindingError", "lower", "lower_node"]
