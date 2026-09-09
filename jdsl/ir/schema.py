"""The serializable Behavior IR (design §21) and first-class residual Signature
(§18/§19).

Humans keep authoring jdsl with the Python combinators; the compiler emits and a
package ships this JSON IR. It is a distribution/implementation format, not the
primary human DSL (§21). The IR is a restricted node vocabulary over the runtime's
primitives — no embedded code, guards are the safe expression language (`expr.py`),
and model leaves reference typed Signatures by id.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

BEHAVIOR_FORMAT = "jdsl.behavior.v1"
SIGNATURE_FORMAT = "jdsl.signature.v1"


# -- residual signature (§18) -------------------------------------------------

@dataclass
class SignatureInput:
    """One input to a residual model leaf: where it comes from and its type."""
    source: str                       # blackboard path, e.g. "blackboard.request" or "request"
    schema: dict[str, Any] = field(default_factory=lambda: {"type": "string"})

    def field_name(self) -> str:
        return self.source.split(".")[-1]


@dataclass
class SignatureOutput:
    name: str
    schema: dict[str, Any] = field(default_factory=lambda: {"type": "string"})


@dataclass
class Signature:
    """A typed interface between one tree leaf and the small model (§18.1). The
    string form `predict("a -> b")` remains the authoring shorthand (§19); this is
    the structured form packages carry."""
    id: str
    kind: str = "predict"             # predict | react
    inputs: dict[str, SignatureInput] = field(default_factory=dict)
    output: SignatureOutput | None = None
    instruction: str = ""
    examples: list[dict[str, Any]] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)   # logical tool ids (react only)
    context_policy: dict[str, Any] = field(default_factory=dict)
    validator: dict[str, Any] = field(default_factory=lambda: {"type": "json_schema"})

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": SIGNATURE_FORMAT,
            "id": self.id,
            "kind": self.kind,
            "inputs": {k: asdict(v) for k, v in self.inputs.items()},
            "output": asdict(self.output) if self.output else None,
            "instruction": self.instruction,
            "examples": self.examples,
            "tools": self.tools,
            "context_policy": self.context_policy,
            "validator": self.validator,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Signature:
        inputs = {k: SignatureInput(source=v.get("source", k), schema=v.get("schema", {"type": "string"}))
                  for k, v in (data.get("inputs") or {}).items()}
        out = data.get("output")
        output = SignatureOutput(name=out["name"], schema=out.get("schema", {"type": "string"})) if out else None
        return cls(
            id=data["id"], kind=data.get("kind", "predict"), inputs=inputs, output=output,
            instruction=data.get("instruction", ""), examples=data.get("examples", []),
            tools=data.get("tools", []), context_policy=data.get("context_policy", {}),
            validator=data.get("validator", {"type": "json_schema"}),
        )


# -- IR nodes (§21.1) ---------------------------------------------------------

@dataclass
class IRNode:
    """Base IR node. `type` is the discriminator; `id` is the stable identity."""
    type: str
    id: str | None = None

    def children(self) -> list[IRNode]:
        return []


@dataclass
class IRComposite(IRNode):
    children_: list[IRNode] = field(default_factory=list)

    def children(self) -> list[IRNode]:
        return list(self.children_)


@dataclass
class IRSequence(IRComposite):
    def __post_init__(self) -> None: self.type = "sequence"


@dataclass
class IRSelector(IRComposite):
    def __post_init__(self) -> None: self.type = "selector"


@dataclass
class IRDecorator(IRNode):
    child: IRNode | None = None

    def children(self) -> list[IRNode]:
        return [self.child] if self.child else []


@dataclass
class IROptional(IRDecorator):
    def __post_init__(self) -> None: self.type = "optional"


@dataclass
class IRInvert(IRDecorator):
    def __post_init__(self) -> None: self.type = "invert"


@dataclass
class IRRepeat(IRDecorator):
    until: IRNode | None = None
    max: int = 3

    def __post_init__(self) -> None: self.type = "repeat"

    def children(self) -> list[IRNode]:
        return ([self.child] if self.child else []) + ([self.until] if self.until else [])


@dataclass
class IRAction(IRNode):
    tool: str = ""                                   # logical capability id
    arguments: dict[str, Any] = field(default_factory=dict)  # {name: {ref|const}}
    store: str | None = None

    def __post_init__(self) -> None: self.type = "action"


@dataclass
class IRGuard(IRNode):
    expression: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: self.type = "guard"


@dataclass
class IRGuardCall(IRNode):
    predicate: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: self.type = "guard_call"


@dataclass
class IRPredict(IRNode):
    signature: str = ""                              # signature id

    def __post_init__(self) -> None: self.type = "predict"


@dataclass
class IRReact(IRNode):
    signature: str = ""

    def __post_init__(self) -> None: self.type = "react"


@dataclass
class BehaviorIR:
    """A whole compiled behavior tree plus the signatures its leaves reference."""
    root: IRNode
    signatures: dict[str, Signature] = field(default_factory=dict)
    format: str = BEHAVIOR_FORMAT

    def to_dict(self) -> dict[str, Any]:
        return {"format": self.format, "root": node_to_dict(self.root)}

    @classmethod
    def from_dict(cls, data: dict[str, Any], signatures: dict[str, Signature] | None = None) -> BehaviorIR:
        return cls(root=node_from_dict(data["root"]), signatures=signatures or {},
                   format=data.get("format", BEHAVIOR_FORMAT))

    def walk(self) -> list[IRNode]:
        out: list[IRNode] = []
        stack = [self.root]
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(reversed(n.children()))
        return out


# -- (de)serialization --------------------------------------------------------

def node_to_dict(node: IRNode) -> dict[str, Any]:
    base: dict[str, Any] = {"type": node.type}
    if node.id is not None:
        base["id"] = node.id
    if isinstance(node, IRComposite):
        base["children"] = [node_to_dict(c) for c in node.children_]
    elif isinstance(node, IRRepeat):
        if node.child: base["child"] = node_to_dict(node.child)
        if node.until: base["until"] = node_to_dict(node.until)
        base["max"] = node.max
    elif isinstance(node, IRDecorator):
        if node.child: base["child"] = node_to_dict(node.child)
    elif isinstance(node, IRAction):
        base["tool"] = node.tool
        if node.arguments: base["arguments"] = node.arguments
        if node.store: base["store"] = node.store
    elif isinstance(node, IRGuard):
        base["expression"] = node.expression
    elif isinstance(node, IRGuardCall):
        base["predicate"] = node.predicate
        if node.arguments: base["arguments"] = node.arguments
    elif isinstance(node, (IRPredict, IRReact)):
        base["signature"] = node.signature
    return base


_COMPOSITES = {"sequence": IRSequence, "selector": IRSelector}
_DECORATORS = {"optional": IROptional, "invert": IRInvert}


def node_from_dict(data: dict[str, Any]) -> IRNode:
    t = data.get("type")
    nid = data.get("id")
    if t in _COMPOSITES:
        return _COMPOSITES[t](type=t, id=nid,
                              children_=[node_from_dict(c) for c in data.get("children", [])])
    if t in _DECORATORS:
        child = data.get("child")
        return _DECORATORS[t](type=t, id=nid, child=node_from_dict(child) if child else None)
    if t == "repeat":
        child = data.get("child")
        until = data.get("until")
        return IRRepeat(type=t, id=nid, child=node_from_dict(child) if child else None,
                        until=node_from_dict(until) if until else None, max=data.get("max", 3))
    if t == "action":
        return IRAction(type=t, id=nid, tool=data.get("tool", ""),
                        arguments=data.get("arguments", {}), store=data.get("store"))
    if t == "guard":
        return IRGuard(type=t, id=nid, expression=data.get("expression", {}))
    if t == "guard_call":
        return IRGuardCall(type=t, id=nid, predicate=data.get("predicate", ""),
                           arguments=data.get("arguments", {}))
    if t == "predict":
        return IRPredict(type=t, id=nid, signature=data.get("signature", ""))
    if t == "react":
        return IRReact(type=t, id=nid, signature=data.get("signature", ""))
    raise ValueError(f"unknown IR node type {t!r}")


VALID_NODE_TYPES = frozenset({
    "sequence", "selector", "optional", "invert", "repeat",
    "action", "guard", "guard_call", "predict", "react",
})


__all__ = [
    "BEHAVIOR_FORMAT", "SIGNATURE_FORMAT", "VALID_NODE_TYPES",
    "Signature", "SignatureInput", "SignatureOutput",
    "IRNode", "IRComposite", "IRSequence", "IRSelector", "IRDecorator",
    "IROptional", "IRInvert", "IRRepeat", "IRAction", "IRGuard", "IRGuardCall",
    "IRPredict", "IRReact", "BehaviorIR", "node_to_dict", "node_from_dict",
]
