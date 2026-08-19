"""Behavior-tree nodes and the tree-walking interpreter (no codegen).

seq=AND, sel=OR, act=call a tool, check=guard on the blackboard, predict=LLM
leaf, root=entry point. Every node ticks to a Status; determinism is in the
tree, the model only at predict.
"""

from __future__ import annotations

import enum
import inspect
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, get_args, get_origin, get_type_hints

from jdsl.context import Ref, RunContext


class Status(enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"

    def __bool__(self) -> bool: return self is Status.SUCCESS


class Node:
    """Base node. Subclasses implement tick; context is scoped to the subtree."""
    context_system: str | None = None

    def tick(self, ctx: RunContext) -> Status: raise NotImplementedError

    def label(self) -> str:
        """Short human-readable label for rendering / write provenance."""
        return type(self).__name__.lower()

    def _children(self) -> list[tuple[str | None, Node]]:
        """(edge-label, child) pairs for rendering. Leaves return []."""
        return []

    def _run_with_context(self, ctx: RunContext, body: Callable[[], Status]) -> Status:
        if self.context_system is None: return body()
        ctx.window.push_system(self.context_system)
        try: return body()
        finally: ctx.window.pop_system()


@dataclass
class Action(Node):
    """Leaf calling a tool. SUCCESS = didn't raise; a returned Status is honored;
    any other return is stored under store_as."""
    fn: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    store_as: str | None = None
    context_system: str | None = None

    def tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            args = tuple(self._resolve(a, ctx) for a in self.args)
            kwargs = {k: self._resolve(v, ctx) for k, v in self.kwargs.items()}
            result = self.fn(*args, **kwargs)
            if isinstance(result, Status): return result
            if self.store_as is not None: ctx.blackboard.set(self.store_as, result, writer=self.label())
            return Status.SUCCESS
        return self._run_with_context(ctx, body)

    def label(self) -> str:
        name = getattr(self.fn, "name", None) or getattr(self.fn, "__name__", "fn")
        return f"act({name})" + (f" -> {self.store_as}" if self.store_as else "")

    @staticmethod
    def _resolve(value: Any, ctx: RunContext) -> Any:
        if not isinstance(value, Ref): return value
        if value.name not in ctx.blackboard:
            raise KeyError(f"ref({value.name!r}) is not on the blackboard yet. Seed it as a run() "
                           "input or produce it in an earlier node (e.g. store(...)).")
        return ctx.blackboard[value.name]


@dataclass
class Sequence(Node):
    """Run children in order; fail fast (AND)."""
    children: list[Node] = field(default_factory=list)
    context_system: str | None = None

    def tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            for child in self.children:
                if child.tick(ctx) is Status.FAILURE: return Status.FAILURE
            return Status.SUCCESS
        return self._run_with_context(ctx, body)

    def label(self) -> str: return "seq"
    def _children(self) -> list[tuple[str | None, Node]]: return [(None, c) for c in self.children]


@dataclass
class Selector(Node):
    """Try children until one succeeds (OR)."""
    children: list[Node] = field(default_factory=list)
    context_system: str | None = None

    def tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            for child in self.children:
                if child.tick(ctx) is Status.SUCCESS: return Status.SUCCESS
            return Status.FAILURE
        return self._run_with_context(ctx, body)

    def label(self) -> str: return "sel"
    def _children(self) -> list[tuple[str | None, Node]]: return [(None, c) for c in self.children]


@dataclass
class Repeat(Node):
    """Run child up to `max` times, stopping early when `until` succeeds (checked
    after each pass). SUCCESS when `until` is satisfied — or when there's no
    `until` (a fixed loop). FAILURE if `max` is reached unsatisfied, or the child
    fails. Behavior-tree repeat/retry decorator; do-while, not while."""
    child: Node
    until: Node | None = None
    max: int = 3
    context_system: str | None = None

    def tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            for _ in range(self.max):
                if self.child.tick(ctx) is Status.FAILURE: return Status.FAILURE
                if self.until is not None and self.until.tick(ctx) is Status.SUCCESS: return Status.SUCCESS
            return Status.SUCCESS if self.until is None else Status.FAILURE
        return self._run_with_context(ctx, body)

    def label(self) -> str: return f"repeat(max={self.max})"
    def _children(self) -> list[tuple[str | None, Node]]:
        return [(None, self.child)] + ([("until", self.until)] if self.until is not None else [])


@dataclass
class Check(Node):
    """Guard leaf: SUCCESS iff blackboard[key] matches equals. String matches are
    lenient — case-insensitive, whitespace- and surrounding-punctuation-trimmed —
    because the value is usually fuzzy model text ("Yes." should match "yes").
    Non-string values compare with plain ==."""
    key: str
    equals: Any
    context_system: str | None = None

    def tick(self, ctx: RunContext) -> Status:
        return Status.SUCCESS if self._match(ctx.blackboard.get(self.key)) else Status.FAILURE

    def label(self) -> str: return f"check({self.key} == {self.equals!r})"

    def _match(self, actual: Any) -> bool:
        if isinstance(actual, str) and isinstance(self.equals, str):
            return self._norm(actual) == self._norm(self.equals)
        return actual == self.equals

    @staticmethod
    def _norm(s: str) -> str: return s.strip().strip(".!?,;:\"'").strip().casefold()


@dataclass
class Predict(Node):
    """DSPy-style LLM leaf: read input fields, ask for output fields as JSON,
    write them back. FAILURE if nothing parseable comes back."""
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    instructions: str | None = None
    context_system: str | None = None

    def tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            model = ctx.require_model()
            # stateless: prompt is built from blackboard inputs + scoped system only.
            # State flows via the blackboard, so leaves don't leak raw output into
            # each other's prompts (and the message list always starts with `user`).
            text = model.generate(system=ctx.window.system,
                                  messages=[{"role": "user", "content": self._build_prompt(ctx)}],
                                  model_id=ctx.model_id)
            # single free-text output: store the reply verbatim (no JSON envelope,
            # which otherwise makes the model reason about the wrapper, not the task).
            if len(self.outputs) == 1:
                text = text.strip()
                if not text: return Status.FAILURE
                ctx.blackboard.set(self.outputs[0], text, writer=self.label())
                return Status.SUCCESS
            parsed = self._parse(text)
            if parsed is None: return Status.FAILURE
            for key in self.outputs: ctx.blackboard.set(key, parsed.get(key), writer=self.label())
            return Status.SUCCESS
        return self._run_with_context(ctx, body)

    def label(self) -> str:
        return f"predict({', '.join(self.inputs)} -> {', '.join(self.outputs)})"

    def _build_prompt(self, ctx: RunContext) -> str:
        lines: list[str] = []
        if self.instructions: lines.append(self.instructions)
        if self.inputs:
            lines.append("Given these inputs:")
            lines += [f"- {name}: {ctx.blackboard.get(name)!r}" for name in self.inputs]
        if len(self.outputs) == 1:
            lines.append(f"Provide {self.outputs[0]} as your entire response — no preamble, no labels, no JSON.")
        else:
            lines.append(f"Respond with ONLY a JSON object containing exactly these keys: "
                         f"{', '.join(self.outputs)}. No prose, no code fences.")
        return "\n".join(lines)

    @staticmethod
    def _parse(text: str) -> dict[str, Any] | None:
        try: return json.loads(text)
        except json.JSONDecodeError: pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match: return None
        try: return json.loads(match.group(0))
        except json.JSONDecodeError: return None


_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _json_type(annotation: Any) -> dict[str, Any]:
    """Map a Python annotation to a JSON-schema fragment. Scalars map directly;
    list/tuple/set map to an array with an `items` type; anything else -> string."""
    if annotation in _JSON_TYPES: return {"type": _JSON_TYPES[annotation]}
    if annotation in (list, tuple, set) or get_origin(annotation) in (list, tuple, set):
        args = get_args(annotation)
        item = _JSON_TYPES.get(args[0], "string") if args else "string"
        return {"type": "array", "items": {"type": item}}
    return {"type": "string"}


def _tool_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    """A JSON schema for fn's parameters, from its signature/annotations. Args
    without a default are required; unannotated args default to string. Uses
    get_type_hints so `from __future__ import annotations` (stringized hints)
    still resolves to real types."""
    try: hints = get_type_hints(fn)
    except Exception: hints = {}  # unresolvable forward refs -> treat all as string
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, p in inspect.signature(fn).parameters.items():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD): continue
        props[name] = _json_type(hints.get(name))
        if p.default is inspect.Parameter.empty: required.append(name)
    return {"type": "object", "properties": props, "required": required}


@dataclass
class React(Node):
    """Agentic LLM leaf: the model reasons and calls @tools in a loop (native
    provider function-calling) until it answers. Reads input fields, runs each
    tool the model picks, feeds results back, and writes the final answer to the
    single output field. FAILURE if the model answers empty or `max_steps` is hit
    without a final answer."""
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    tools: list[Any] = field(default_factory=list)
    instructions: str | None = None
    max_steps: int = 6
    context_system: str | None = None

    def tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            model = ctx.require_model()
            by_name = {t.name: t for t in self.tools}
            # Honor an explicit JSON schema on the tool (e.g. tau-bench tools wrapped
            # as `**kwargs` bridges, where introspecting `fn` yields empty props and
            # the model would have to guess argument names); fall back to signature
            # introspection for plain @tools. Matches Session flat mode.
            specs = [{"name": t.name, "description": t.description,
                      "parameters": getattr(t, "parameters", None) or _tool_schema(t.fn)}
                     for t in self.tools]
            history: list[dict[str, Any]] = [{"role": "user", "content": self._build_prompt(ctx)}]
            for _ in range(self.max_steps):
                turn = model.converse(system=ctx.window.system, messages=history,
                                      tools=specs, model_id=ctx.model_id)
                if not turn.tool_calls:
                    answer = turn.text.strip()
                    if not answer: return Status.FAILURE
                    ctx.blackboard.set(self.outputs[0], answer, writer=self.label())
                    return Status.SUCCESS
                history.append({"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls})
                for call in turn.tool_calls:
                    tool = by_name.get(call.name)
                    result = tool(**call.arguments) if tool else f"error: no tool named {call.name!r}"
                    history.append({"role": "tool", "tool_call_id": call.id,
                                    "name": call.name, "content": str(result)})
            return Status.FAILURE  # ran out of steps without a final answer
        return self._run_with_context(ctx, body)

    def _build_prompt(self, ctx: RunContext) -> str:
        lines: list[str] = []
        if self.instructions: lines.append(self.instructions)
        if self.inputs:
            lines.append("Given these inputs:")
            lines += [f"- {name}: {ctx.blackboard.get(name)!r}" for name in self.inputs]
        lines.append("Use the available tools as needed, then give your final answer as plain text.")
        return "\n".join(lines)

    def label(self) -> str:
        names = ", ".join(t.name for t in self.tools)
        return f"react({', '.join(self.inputs)} -> {', '.join(self.outputs)}, tools=[{names}])"


@dataclass
class Decorator(Node):
    """Base for single-child wrappers ('a behaviour wearing a different hat'):
    they transform a child's status without introducing a new composite type."""
    child: Node
    context_system: str | None = None

    def _children(self) -> list[tuple[str | None, Node]]: return [(None, self.child)]


@dataclass
class Invert(Decorator):
    """Flip the child's status: SUCCESS <-> FAILURE."""
    def tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            return Status.FAILURE if self.child.tick(ctx) is Status.SUCCESS else Status.SUCCESS
        return self._run_with_context(ctx, body)

    def label(self) -> str: return "invert"


@dataclass
class Optional(Decorator):
    """Fail-soft: run the child but always report SUCCESS, so a failing step never
    aborts its parent sequence (py_trees' FailureIsSuccess)."""
    def tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            self.child.tick(ctx)
            return Status.SUCCESS
        return self._run_with_context(ctx, body)

    def label(self) -> str: return "optional"


@dataclass
class Timeout(Decorator):
    """Run the child with a wall-clock bound; FAILURE if it doesn't finish in
    `seconds`. The child runs in a worker thread — on timeout it is abandoned
    (Python can't kill it), so use this for read-only/idempotent work like an LLM
    or lookup call."""
    seconds: float = 30.0

    def tick(self, ctx: RunContext) -> Status:
        import concurrent.futures
        def body() -> Status:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.child.tick, ctx)
                try: return future.result(timeout=self.seconds)
                except concurrent.futures.TimeoutError: return Status.FAILURE
        return self._run_with_context(ctx, body)

    def label(self) -> str: return f"timeout({self.seconds}s)"


@dataclass
class OneShot(Decorator):
    """Run the child at most once per run; latch and replay its status on any
    later tick (only observable inside a repeat/loop). State is per-run."""
    def tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            key = id(self)
            if key not in ctx.state:
                ctx.state[key] = self.child.tick(ctx)
            return ctx.state[key]
        return self._run_with_context(ctx, body)

    def label(self) -> str: return "oneshot"


@dataclass
class Root(Node):
    """Entry point: one child + name/system/model. Also a builder."""
    name: str
    child: Node | None = None
    context_system: str | None = None
    model_id: str | None = None

    def model(self, model_id: str) -> Root: self.model_id = model_id; return self
    def do(self, child: Node) -> Root: self.child = child; return self

    def tick(self, ctx: RunContext) -> Status:
        if self.child is None: raise RuntimeError(f"Root {self.name!r} has no child; call .do(...) on it.")
        if ctx.model_id is None: ctx.model_id = self.model_id
        return self._run_with_context(ctx, lambda: self.child.tick(ctx))

    def label(self) -> str:
        return f"root {self.name!r}" + (f" [{self.model_id}]" if self.model_id else "")

    def _children(self) -> list[tuple[str | None, Node]]:
        return [(None, self.child)] if self.child is not None else []

    def run(self, *, model: Any = None, **inputs: Any) -> RunContext:
        """Execute the skill and return the final RunContext (read ctx.blackboard)."""
        from jdsl.context import Blackboard
        if model is None and self.model_id is not None:
            from jdsl.provider import LanguageModel
            model = LanguageModel.from_config()
        ctx = RunContext(blackboard=Blackboard(inputs), model=model, model_id=self.model_id)
        self.tick(ctx)
        return ctx
