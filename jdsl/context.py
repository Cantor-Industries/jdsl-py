"""Runtime state threaded through a run: the blackboard, the context window,
and the model handle. Nodes read/write the blackboard and scope system text on
the window as the tree is walked."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid an import cycle with provider
    from jdsl.provider import LanguageModel


class Blackboard(dict[str, Any]):
    """Shared key/value store for one run. predict reads inputs, writes outputs."""


@dataclass(frozen=True)
class Ref:
    """Placeholder for blackboard[name], resolved when an act runs."""
    name: str


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

    def require_model(self) -> LanguageModel:
        if self.model is None:
            raise RuntimeError("This skill uses an LLM leaf (predict) but no model is attached. "
                               "Give the root a model, e.g. root(...).model('claude-opus-4-8').")
        return self.model
