"""The authoring surface: combinators. You build a skill by nesting calls, not
tagged literals — the tree structure is the call structure. act is typed with
ParamSpec, so literal args are checked against the tool's real signature."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar, overload

from jdsl.context import Ref
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

P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class Tool:
    """Named, still-callable wrapper around a function; carries name/description
    used by react to expose it to the model for function-calling."""
    fn: Callable[..., Any]
    name: str
    description: str = ""

    def __call__(self, *args: Any, **kwargs: Any) -> Any: return self.fn(*args, **kwargs)


@overload
def tool(fn: Callable[P, R]) -> Callable[P, R]: ...
@overload
def tool(*, name: str | None = ..., description: str | None = ...) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def tool(fn: Callable[P, R] | None = None, *, name: str | None = None, description: str | None = None) -> Any:
    """Register a callable as a tool. Bare (@tool) or with args (@tool(description=...))."""
    def wrap(f: Callable[P, R]) -> Tool:
        return Tool(fn=f, name=name or getattr(f, "__name__", "tool"),
                    description=description or (f.__doc__ or "").strip())
    return wrap(fn) if fn is not None else wrap


def _ident(node: Node, node_id: str | None) -> Node:
    """Attach an optional stable id to a node (§20). Returns the node for chaining."""
    if node_id is not None: node.node_id = node_id
    return node


def act(fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs) -> Action:
    """Leaf calling fn(*args, **kwargs). Literal args are type-checked; a ref(...)
    arg resolves from the blackboard at run time. Wrap with store to capture the result.

    Pass an `id=` (as a kwarg) to give the node a stable compiled identity (§20);
    it is popped before the call so it never reaches the tool."""
    node_id = kwargs.pop("id", None)
    return _ident(Action(fn=fn, args=args, kwargs=kwargs), node_id)  # type: ignore[arg-type]


def ref(name: str) -> Ref:
    """A blackboard reference for an act argument: act(fetch, ref("query"))."""
    return Ref(name)


def store(node: Action, key: str) -> Action:
    """Capture an action's return value onto the blackboard under key."""
    node.store_as = key
    return node


def seq(*children: Node, context: str | None = None, id: str | None = None) -> Sequence:
    """Run children in order; fail fast (AND)."""
    return _ident(Sequence(children=list(children), context_system=context), id)  # type: ignore[return-value]


def sel(*children: Node, context: str | None = None, id: str | None = None) -> Selector:
    """Try children until one succeeds (OR)."""
    return _ident(Selector(children=list(children), context_system=context), id)  # type: ignore[return-value]


def check(key: str, equals: Any, *, id: str | None = None) -> Check:
    """Guard leaf: succeeds iff blackboard[key] == equals."""
    return _ident(Check(key=key, equals=equals), id)  # type: ignore[return-value]


def guard(expression: dict[str, Any], *, id: str | None = None) -> Guard:
    """Compiled state predicate over the blackboard using the restricted expression
    language (§21.2), e.g. guard({"in": [{"ref": "order.status"}, ["pending"]]})."""
    return _ident(Guard(expression=expression), id)  # type: ignore[return-value]


def guard_call(predicate: Callable[..., Any], arguments: dict[str, Any] | None = None, *,
               predicate_id: str | None = None, id: str | None = None) -> GuardCall:
    """Guard backed by a trusted runtime predicate (§21.2). arguments may contain
    ref(...) values resolved from the blackboard at run time."""
    node = GuardCall(predicate=predicate, arguments=arguments or {}, predicate_id=predicate_id)
    return _ident(node, id)  # type: ignore[return-value]


def repeat(child: Node, *, until: Node | None = None, max: int = 3, context: str | None = None,
           id: str | None = None) -> Repeat:
    """Run child up to `max` times, stopping early when `until` (e.g. a check) succeeds."""
    return _ident(Repeat(child=child, until=until, max=max, context_system=context), id)  # type: ignore[return-value]


def invert(child: Node, *, context: str | None = None, id: str | None = None) -> Invert:
    """Flip a child's status: SUCCESS <-> FAILURE (e.g. invert(check(...)))."""
    return _ident(Invert(child=child, context_system=context), id)  # type: ignore[return-value]


def optional(child: Node, *, context: str | None = None, id: str | None = None) -> Optional:
    """Fail-soft wrapper: run the child but always succeed, so it can't abort a seq."""
    return _ident(Optional(child=child, context_system=context), id)  # type: ignore[return-value]


def timeout(child: Node, *, seconds: float = 30.0, context: str | None = None, id: str | None = None) -> Timeout:
    """Bound a child to `seconds` of wall-clock time; FAILURE if it overruns."""
    return _ident(Timeout(child=child, seconds=seconds, context_system=context), id)  # type: ignore[return-value]


def oneshot(child: Node, *, context: str | None = None, id: str | None = None) -> OneShot:
    """Run the child at most once per run; replay its status on later ticks."""
    return _ident(OneShot(child=child, context_system=context), id)  # type: ignore[return-value]


def predict(signature: str, *, instructions: str | None = None, context: str | None = None,
            id: str | None = None) -> Predict:
    """DSPy-style LLM leaf from a signature like "question -> answer"."""
    inputs, outputs = _parse_signature(signature)
    return _ident(Predict(inputs=inputs, outputs=outputs, instructions=instructions,  # type: ignore[return-value]
                          context_system=context), id)


def react(signature: str, *, tools: list[Any], instructions: str | None = None,
          max_steps: int = 6, context: str | None = None, id: str | None = None) -> React:
    """Agentic LLM leaf: the model reasons and calls the given @tools in a loop
    (native function-calling) until it answers. Signature is "inputs -> answer"
    with a single output field."""
    inputs, outputs = _parse_signature(signature)
    if len(outputs) != 1:
        raise ValueError(f"react signature {signature!r} must have exactly one output (the answer).")
    return _ident(React(inputs=inputs, outputs=outputs, tools=list(tools),  # type: ignore[return-value]
                        instructions=instructions, max_steps=max_steps, context_system=context), id)


def root(name: str, *, system: str | None = None) -> Root:
    """Entry point of a skill. Chain .model(id) and .do(child)."""
    return Root(name=name, context_system=system)


def _parse_signature(signature: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if "->" not in signature:
        raise ValueError(f"Signature {signature!r} must contain '->', e.g. 'question -> answer'.")
    lhs, rhs = signature.split("->", 1)
    inputs = tuple(f.strip() for f in lhs.split(",") if f.strip())
    outputs = tuple(f.strip() for f in rhs.split(",") if f.strip())
    if not outputs:
        raise ValueError(f"Signature {signature!r} declares no output fields.")
    return inputs, outputs
