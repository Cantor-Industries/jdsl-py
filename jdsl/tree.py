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
    """Base node. Subclasses implement `_tick`; `tick` wraps it with trace
    emission (node.enter/node.exit, §35 PR1). Context is scoped to the subtree.

    `node_id` is the optional stable identity used by compiled artifacts (§20):
    author-supplied via the DSL `id=` argument, otherwise a path-derived runtime
    id is assigned by `assign_runtime_ids` when a run is being traced. Tree path
    is deliberately not the *persistent* identity — a compiler may insert nodes."""
    context_system: str | None = None
    node_id: str | None = None
    _runtime_id: str | None = None

    def _tick(self, ctx: RunContext) -> Status: raise NotImplementedError

    def tick(self, ctx: RunContext) -> Status:
        """Public entry: emit enter/exit around the subclass `_tick` when tracing."""
        if ctx.trace_sink is None:
            return self._tick(ctx)
        from jdsl.trace.events import EventKind
        enter = ctx.emit(EventKind.NODE_ENTER, payload=self._trace_meta())
        parent = enter.event_id if enter is not None else None
        status = self._tick(ctx)
        ctx.emit(EventKind.NODE_EXIT, parent_event_id=parent,
                 payload={**self._trace_meta(), "status": status.value})
        return status

    def effective_id(self) -> str | None:
        """The id used in traces/IR: author id if set, else the runtime path id."""
        return self.node_id or self._runtime_id

    def _trace_meta(self) -> dict[str, Any]:
        return {"node_id": self.effective_id(), "type": type(self).__name__.lower(),
                "label": self.label()}

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

    def _tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            args = tuple(self._resolve(a, ctx) for a in self.args)
            kwargs = {k: self._resolve(v, ctx) for k, v in self.kwargs.items()}
            # Tier-A gateway capture (§8.1): record the *resolved* tool arguments so
            # the compiler can mine exact dataflow. Without this an Action calls fn
            # directly and its arguments never appear in the trace.
            self._emit_call(ctx, args, kwargs)
            try:
                result = self.fn(*args, **kwargs)
            except Exception as err:  # noqa: BLE001 — record the failure, then re-raise
                self._emit_result(ctx, error=err)
                raise
            self._emit_result(ctx, result=result)
            if isinstance(result, Status): return result
            if self.store_as is not None: ctx.blackboard.set(self.store_as, result, writer=self.label())
            return Status.SUCCESS
        return self._run_with_context(ctx, body)

    def _tool_name(self) -> str:
        return getattr(self.fn, "name", None) or getattr(self.fn, "__name__", "fn")

    def _emit_call(self, ctx: RunContext, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        if ctx.trace_sink is None: return
        from jdsl.trace.events import EventKind
        arguments = dict(kwargs)
        for i, a in enumerate(args): arguments[f"_arg{i}"] = a
        started = ctx.emit(EventKind.TOOL_CALL_STARTED, actor="model", payload={
            "node_id": self.effective_id(), "store": self.store_as,
            "tool": {"host_name": self._tool_name(), "logical_id": None}, "arguments": arguments})
        self._call_event_id = started.event_id if started is not None else None

    def _emit_result(self, ctx: RunContext, *, result: Any = None, error: Any = None) -> None:
        if ctx.trace_sink is None: return
        from jdsl.trace.events import EventKind
        parent = getattr(self, "_call_event_id", None)
        if error is not None or _looks_like_error(result):
            ctx.emit(EventKind.TOOL_CALL_FAILED, actor="tool", parent_event_id=parent, payload={
                "node_id": self.effective_id(), "tool": {"host_name": self._tool_name()},
                "error": str(error if error is not None else result)})
        else:
            ctx.emit(EventKind.TOOL_CALL_COMPLETED, actor="tool", parent_event_id=parent, payload={
                "node_id": self.effective_id(), "store": self.store_as,
                "tool": {"host_name": self._tool_name()},
                "result": result if not isinstance(result, Status) else result.value})

    def label(self) -> str:
        name = getattr(self.fn, "name", None) or getattr(self.fn, "__name__", "fn")
        return f"act({name})" + (f" -> {self.store_as}" if self.store_as else "")

    @staticmethod
    def _resolve(value: Any, ctx: RunContext) -> Any:
        if not isinstance(value, Ref): return value
        if value.name in ctx.blackboard:
            return ctx.blackboard[value.name]
        # Compiled refs may be JSON paths (e.g. "orders[$selected_index].id", §21.1)
        # rather than a bare key. Fall back to the restricted path resolver.
        from jdsl.ir.expr import _MISSING, resolve_path
        resolved = resolve_path(value.name, ctx.blackboard)
        if resolved is _MISSING:
            raise KeyError(f"ref({value.name!r}) is not on the blackboard yet. Seed it as a run() "
                           "input or produce it in an earlier node (e.g. store(...)).")
        return resolved


@dataclass
class Sequence(Node):
    """Run children in order; fail fast (AND)."""
    children: list[Node] = field(default_factory=list)
    context_system: str | None = None

    def _tick(self, ctx: RunContext) -> Status:
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

    def _tick(self, ctx: RunContext) -> Status:
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

    def _tick(self, ctx: RunContext) -> Status:
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

    def _tick(self, ctx: RunContext) -> Status:
        return Status.SUCCESS if self._match(ctx.blackboard.get(self.key)) else Status.FAILURE

    def label(self) -> str: return f"check({self.key} == {self.equals!r})"

    def _match(self, actual: Any) -> bool:
        if isinstance(actual, str) and isinstance(self.equals, str):
            return self._norm(actual) == self._norm(self.equals)
        return actual == self.equals

    @staticmethod
    def _norm(s: str) -> str: return s.strip().strip(".!?,;:\"'").strip().casefold()


@dataclass
class Guard(Node):
    """Compiled state predicate (§21.2): SUCCESS iff the restricted expression is
    true over the blackboard. This is the general guard `check` is too narrow for
    (§5.4) — it reads refs/paths and combines them with eq/in/and/or/… . The
    expression is a safe JSON tree, never arbitrary code."""
    expression: dict[str, Any]
    context_system: str | None = None

    def _tick(self, ctx: RunContext) -> Status:
        from jdsl.ir.expr import evaluate
        return Status.SUCCESS if evaluate(self.expression, ctx.blackboard) else Status.FAILURE

    def label(self) -> str:
        op = next(iter(self.expression), "?") if isinstance(self.expression, dict) else "?"
        return f"guard({op})"


@dataclass
class GuardCall(Node):
    """Guard backed by a trusted runtime predicate (§21.2 `guard_call`). Domain
    logic that exceeds the expression system references a named capability the
    runtime supplies; the package only names it, it never ships its code."""
    predicate: Callable[..., Any]
    arguments: dict[str, Any] = field(default_factory=dict)
    predicate_id: str | None = None
    context_system: str | None = None

    def _tick(self, ctx: RunContext) -> Status:
        args = {k: Action._resolve(v, ctx) for k, v in self.arguments.items()}
        return Status.SUCCESS if self.predicate(**args) else Status.FAILURE

    def label(self) -> str: return f"guard_call({self.predicate_id or getattr(self.predicate, '__name__', '?')})"


@dataclass
class Predict(Node):
    """DSPy-style LLM leaf: read input fields, ask for output fields as JSON,
    write them back. FAILURE if nothing parseable comes back.

    `output_schemas` (compiled signatures, §18) attaches a JSON-schema fragment
    per output; when present the parsed value is coerced to the declared type and
    validated (integer index, enum, …) before it is written. Absent (the authoring
    default) leaves behavior unchanged — a single free-text output stored verbatim."""
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    instructions: str | None = None
    context_system: str | None = None
    output_schemas: dict[str, dict[str, Any]] | None = None

    def _tick(self, ctx: RunContext) -> Status:
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
                value, ok = self._coerce(self.outputs[0], text)
                if not ok: return Status.FAILURE
                ctx.blackboard.set(self.outputs[0], value, writer=self.label())
                return Status.SUCCESS
            parsed = self._parse(text)
            if parsed is None: return Status.FAILURE
            for key in self.outputs:
                value, ok = self._coerce(key, parsed.get(key))
                if not ok: return Status.FAILURE
                ctx.blackboard.set(key, value, writer=self.label())
            return Status.SUCCESS
        return self._run_with_context(ctx, body)

    def _coerce(self, key: str, value: Any) -> tuple[Any, bool]:
        """Coerce/validate `value` against the output schema for `key`. Returns
        (value, ok); ok=False signals a validation failure (leaf -> FAILURE)."""
        schema = (self.output_schemas or {}).get(key)
        if not schema: return value, True
        typ = schema.get("type")
        try:
            if typ == "integer" and not isinstance(value, bool):
                value = int(str(value).strip())
            elif typ == "number" and not isinstance(value, bool):
                value = float(str(value).strip())
            elif typ == "boolean":
                value = str(value).strip().lower() in ("true", "yes", "1")
            elif typ == "string":
                value = str(value)
        except (TypeError, ValueError):
            return value, False
        enum = schema.get("enum")
        if enum is not None and value not in enum:
            return value, False
        if "minimum" in schema and isinstance(value, (int, float)) and value < schema["minimum"]:
            return value, False
        return value, True

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


def _looks_like_error(result: Any) -> bool:
    """Heuristic for a tool observation that reports failure — used only to label
    a trace event tool.call.completed vs tool.call.failed. tau-bench and most
    tools prefix errors with 'Error: ...'; jdsl's own bridges use 'error:'."""
    return str(result).strip().lower().startswith("error")


def assign_runtime_ids(root: Node) -> None:
    """Assign path-derived `_runtime_id`s to every node lacking an author id (§20).

    The id is the structural path from the root (e.g. `root/seq.0/act.1`). It is a
    *runtime* identity only — stable across a single tree's formatting, but the
    persistent package identity is the author-supplied `node_id`, since a compiler
    may insert nodes and shift paths."""
    def walk(node: Node, path: str) -> None:
        node._runtime_id = node._runtime_id or path
        for i, (_edge, child) in enumerate(node._children()):
            walk(child, f"{path}/{type(child).__name__.lower()}.{i}")
    walk(root, type(root).__name__.lower())


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

    def _tick(self, ctx: RunContext) -> Status:
        # PR2: react is the largest trace gap in the runtime — its internal tool
        # trajectory used to stay local and only the final answer hit the
        # blackboard. We emit the whole loop (model turns + every tool call) so
        # the compiler can mine dataflow, recovery, and tool visibility (§5.4).
        from jdsl.trace.events import EventKind

        def body() -> Status:
            model = ctx.require_model()
            by_name = {t.name: t for t in self.tools}
            specs = [{"name": t.name, "description": t.description, "parameters": _tool_schema(t.fn)}
                     for t in self.tools]
            ctx.emit(EventKind.REACT_STARTED, payload={"node_id": self.effective_id(),
                     "inputs": list(self.inputs), "outputs": list(self.outputs)})
            ctx.emit(EventKind.TOOLSET_EXPOSED, payload={"node_id": self.effective_id(),
                     "tools": [{"host_name": t.name, "description": t.description} for t in self.tools]})
            history: list[dict[str, Any]] = [{"role": "user", "content": self._build_prompt(ctx)}]
            for _ in range(self.max_steps):
                ctx.emit(EventKind.MODEL_REQUESTED, actor="model",
                         payload={"node_id": self.effective_id(), "tools": [t.name for t in self.tools]})
                turn = model.converse(system=ctx.window.system, messages=history,
                                      tools=specs, model_id=ctx.model_id)
                ctx.emit(EventKind.MODEL_RESPONDED, actor="model", payload={
                    "node_id": self.effective_id(), "text": turn.text,
                    "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in turn.tool_calls]})
                if not turn.tool_calls:
                    answer = turn.text.strip()
                    if not answer:
                        ctx.emit(EventKind.REACT_FINISHED, payload={"node_id": self.effective_id(),
                                 "status": Status.FAILURE.value})
                        return Status.FAILURE
                    ctx.blackboard.set(self.outputs[0], answer, writer=self.label())
                    ctx.emit(EventKind.REACT_FINISHED, payload={"node_id": self.effective_id(),
                             "status": Status.SUCCESS.value})
                    return Status.SUCCESS
                history.append({"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls})
                for call in turn.tool_calls:
                    tool = by_name.get(call.name)
                    started = ctx.emit(EventKind.TOOL_CALL_STARTED, actor="model", payload={
                        "node_id": self.effective_id(),
                        "tool": {"host_name": call.name, "logical_id": None},
                        "arguments": call.arguments})
                    parent = started.event_id if started is not None else None
                    try:
                        result = tool(**call.arguments) if tool else f"error: no tool named {call.name!r}"
                    except Exception as err:  # noqa: BLE001 — surface tool errors to the model, don't crash
                        result = f"error: {err}"
                    if _looks_like_error(result) or tool is None:
                        ctx.emit(EventKind.TOOL_CALL_FAILED, actor="tool", parent_event_id=parent,
                                 payload={"node_id": self.effective_id(),
                                          "tool": {"host_name": call.name}, "error": str(result)})
                    else:
                        ctx.emit(EventKind.TOOL_CALL_COMPLETED, actor="tool", parent_event_id=parent,
                                 payload={"node_id": self.effective_id(),
                                          "tool": {"host_name": call.name}, "result": result})
                    history.append({"role": "tool", "tool_call_id": call.id,
                                    "name": call.name, "content": str(result)})
            ctx.emit(EventKind.REACT_FINISHED, payload={"node_id": self.effective_id(),
                     "status": Status.FAILURE.value})
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
    def _tick(self, ctx: RunContext) -> Status:
        def body() -> Status:
            return Status.FAILURE if self.child.tick(ctx) is Status.SUCCESS else Status.SUCCESS
        return self._run_with_context(ctx, body)

    def label(self) -> str: return "invert"


@dataclass
class Optional(Decorator):
    """Fail-soft: run the child but always report SUCCESS, so a failing step never
    aborts its parent sequence (py_trees' FailureIsSuccess)."""
    def _tick(self, ctx: RunContext) -> Status:
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

    def _tick(self, ctx: RunContext) -> Status:
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
    def _tick(self, ctx: RunContext) -> Status:
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

    def _tick(self, ctx: RunContext) -> Status:
        if self.child is None: raise RuntimeError(f"Root {self.name!r} has no child; call .do(...) on it.")
        if ctx.model_id is None: ctx.model_id = self.model_id
        return self._run_with_context(ctx, lambda: self.child.tick(ctx))

    def label(self) -> str:
        return f"root {self.name!r}" + (f" [{self.model_id}]" if self.model_id else "")

    def _children(self) -> list[tuple[str | None, Node]]:
        return [(None, self.child)] if self.child is not None else []

    def run(self, *, model: Any = None, trace_sink: Any = None, capture_id: str = "cap_local",
            episode_id: str = "ep_local", trace_source: Any = None, **inputs: Any) -> RunContext:
        """Execute the skill and return the final RunContext (read ctx.blackboard).

        Pass a `trace_sink` to capture a canonical event stream for this run
        (episode `episode_id` under `capture_id`); omit it and the run is
        untraced and behaves exactly as before."""
        from jdsl.context import Blackboard
        if model is None and self.model_id is not None:
            from jdsl.provider import LanguageModel
            model = LanguageModel.from_config()
        if trace_sink is not None:
            assign_runtime_ids(self)
        ctx = RunContext(blackboard=Blackboard(inputs), model=model, model_id=self.model_id,
                         trace_sink=trace_sink, capture_id=capture_id, episode_id=episode_id,
                         trace_source=trace_source)
        if trace_sink is not None:
            from jdsl.trace.events import EventKind
            ctx.emit(EventKind.EPISODE_STARTED, payload={"skill": self.name, "inputs": dict(inputs)})
        self.tick(ctx)
        if trace_sink is not None:
            from jdsl.trace.events import EventKind
            ctx.emit(EventKind.EPISODE_FINISHED, payload={"skill": self.name})
        return ctx
