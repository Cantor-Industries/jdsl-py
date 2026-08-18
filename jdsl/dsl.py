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
    used by react to expose it to the model for function-calling. `parameters` is
    an optional explicit JSON-schema for the arguments — set it when the schema
    can't be introspected from the fn (e.g. a `**kwargs` bridge to an external
    tool environment); leave it None to derive the schema from the signature."""
    fn: Callable[..., Any]
    name: str
    description: str = ""
    parameters: dict[str, Any] | None = None

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


def act(fn: Callable[P, Any], *args: P.args, **kwargs: P.kwargs) -> Action:
    """Leaf calling fn(*args, **kwargs). Literal args are type-checked; a ref(...)
    arg resolves from the blackboard at run time. Wrap with store to capture the result."""
    return Action(fn=fn, args=args, kwargs=kwargs)


def ref(name: str) -> Ref:
    """A blackboard reference for an act argument: act(fetch, ref("query"))."""
    return Ref(name)


def store(node: Action, key: str) -> Action:
    """Capture an action's return value onto the blackboard under key."""
    node.store_as = key
    return node


def seq(*children: Node, context: str | None = None) -> Sequence:
    """Run children in order; fail fast (AND)."""
    return Sequence(children=list(children), context_system=context)


def sel(*children: Node, context: str | None = None) -> Selector:
    """Try children until one succeeds (OR)."""
    return Selector(children=list(children), context_system=context)


def check(key: str, equals: Any) -> Check:
    """Guard leaf: succeeds iff blackboard[key] == equals."""
    return Check(key=key, equals=equals)


def repeat(child: Node, *, until: Node | None = None, max: int = 3, context: str | None = None) -> Repeat:
    """Run child up to `max` times, stopping early when `until` (e.g. a check) succeeds."""
    return Repeat(child=child, until=until, max=max, context_system=context)


def invert(child: Node, *, context: str | None = None) -> Invert:
    """Flip a child's status: SUCCESS <-> FAILURE (e.g. invert(check(...)))."""
    return Invert(child=child, context_system=context)


def optional(child: Node, *, context: str | None = None) -> Optional:
    """Fail-soft wrapper: run the child but always succeed, so it can't abort a seq."""
    return Optional(child=child, context_system=context)


def timeout(child: Node, *, seconds: float = 30.0, context: str | None = None) -> Timeout:
    """Bound a child to `seconds` of wall-clock time; FAILURE if it overruns."""
    return Timeout(child=child, seconds=seconds, context_system=context)


def oneshot(child: Node, *, context: str | None = None) -> OneShot:
    """Run the child at most once per run; replay its status on later ticks."""
    return OneShot(child=child, context_system=context)


def predict(signature: str, *, instructions: str | None = None, context: str | None = None) -> Predict:
    """DSPy-style LLM leaf from a signature like "question -> answer"."""
    inputs, outputs = _parse_signature(signature)
    return Predict(inputs=inputs, outputs=outputs, instructions=instructions, context_system=context)


def react(signature: str, *, tools: list[Any], instructions: str | None = None,
          max_steps: int = 6, context: str | None = None) -> React:
    """Agentic LLM leaf: the model reasons and calls the given @tools in a loop
    (native function-calling) until it answers. Signature is "inputs -> answer"
    with a single output field."""
    inputs, outputs = _parse_signature(signature)
    if len(outputs) != 1:
        raise ValueError(f"react signature {signature!r} must have exactly one output (the answer).")
    return React(inputs=inputs, outputs=outputs, tools=list(tools),
                 instructions=instructions, max_steps=max_steps, context_system=context)


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
