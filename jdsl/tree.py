"""Behavior-tree nodes and the tree-walking interpreter (no codegen).

seq=AND, sel=OR, act=call a tool, check=guard on the blackboard, predict=LLM
leaf, root=entry point. Every node ticks to a Status; determinism is in the
tree, the model only at predict.
"""

from __future__ import annotations

import enum
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jdsl.context import Ref, RunContext


class Status(enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"

    def __bool__(self) -> bool: return self is Status.SUCCESS


class Node:
    """Base node. Subclasses implement tick; context is scoped to the subtree."""
    context_system: str | None = None

    def tick(self, ctx: RunContext) -> Status: raise NotImplementedError

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
            if self.store_as is not None: ctx.blackboard[self.store_as] = result
            return Status.SUCCESS
        return self._run_with_context(ctx, body)

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


@dataclass
class Check(Node):
    """Guard leaf: SUCCESS iff blackboard[key] == equals."""
    key: str
    equals: Any
    context_system: str | None = None

    def tick(self, ctx: RunContext) -> Status:
        return Status.SUCCESS if ctx.blackboard.get(self.key) == self.equals else Status.FAILURE


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
                ctx.blackboard[self.outputs[0]] = text
                return Status.SUCCESS
            parsed = self._parse(text)
            if parsed is None: return Status.FAILURE
            for key in self.outputs: ctx.blackboard[key] = parsed.get(key)
            return Status.SUCCESS
        return self._run_with_context(ctx, body)

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

    def run(self, *, model: Any = None, **inputs: Any) -> RunContext:
        """Execute the skill and return the final RunContext (read ctx.blackboard)."""
        from jdsl.context import Blackboard
        if model is None and self.model_id is not None:
            from jdsl.provider import LanguageModel
            model = LanguageModel.from_config()
        ctx = RunContext(blackboard=Blackboard(inputs), model=model, model_id=self.model_id)
        self.tick(ctx)
        return ctx
