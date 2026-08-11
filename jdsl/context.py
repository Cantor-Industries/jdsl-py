"""Runtime state threaded through a run: the blackboard, the context window,
and the model handle. Nodes read/write the blackboard and scope system text on
the window as the tree is walked."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid an import cycle with provider
    from jdsl.provider import LanguageModel


@dataclass
class Write:
    """One record of a blackboard write: what, to what, by whom, over what."""
    key: str
    value: Any
    writer: str
    previous: Any = None
    overwrote: bool = False  # a *different* writer had already set this key


class Blackboard(dict[str, Any]):
    """Shared key/value store for one run — a dict with provenance. Every write is
    recorded in `activity` with its writer, and overwrites by a different writer are
    flagged (the silent-clobber bug when two leaves share an output name). Read with
    normal dict access; write via set(key, value, writer=...) to attribute it."""

    def __init__(self, initial: dict[str, Any] | None = None, /, **kwargs: Any) -> None:
        super().__init__()
        self.activity: list[Write] = []
        self._writer: dict[str, str] = {}
        for k, v in {**(initial or {}), **kwargs}.items():
            self.set(k, v, writer="input")

    def set(self, key: str, value: Any, *, writer: str = "?") -> Any:
        prev = self.get(key)
        overwrote = key in self and self._writer.get(key) not in (None, writer)
        super().__setitem__(key, value)
        self._writer[key] = writer
        self.activity.append(Write(key, value, writer, prev, overwrote))
        return value

    def __setitem__(self, key: str, value: Any) -> None: self.set(key, value)

    def who_wrote(self, key: str) -> str | None: return self._writer.get(key)

    def clobbers(self) -> list[Write]: return [w for w in self.activity if w.overwrote]


@dataclass(frozen=True)
class Ref:
    """Placeholder for blackboard[name], resolved when an act runs."""
    name: str


@dataclass
class ToolCall:
    """A provider-neutral tool call the model asked for: name + parsed arguments."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelTurn:
    """One provider-neutral assistant turn: free text and/or tool calls. Empty
    tool_calls means the model is done and `text` is its final answer."""
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ContextWindow:
    """A stack of system fragments, pushed/popped so context is subtree-scoped."""
    _system: list[str] = field(default_factory=list)

    def push_system(self, text: str) -> None: self._system.append(text)
    def pop_system(self) -> None:
        if self._system: self._system.pop()

    @property
    def system(self) -> str: return "\n\n".join(self._system)


@dataclass
class RunContext:
    blackboard: Blackboard = field(default_factory=Blackboard)
    window: ContextWindow = field(default_factory=ContextWindow)
    model: LanguageModel | None = None
    model_id: str | None = None
    state: dict[int, Any] = field(default_factory=dict)  # per-run scratch for stateful nodes (oneshot)

    def __post_init__(self) -> None:
        # accept a plain dict for convenience; upgrade it to a tracked Blackboard.
        if not isinstance(self.blackboard, Blackboard):
            self.blackboard = Blackboard(self.blackboard)

    def require_model(self) -> LanguageModel:
        if self.model is None:
            raise RuntimeError("This skill uses an LLM leaf (predict) but no model is attached. "
                               "Give the root a model, e.g. root(...).model('claude-opus-4-8').")
        return self.model
