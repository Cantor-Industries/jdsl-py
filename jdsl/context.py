"""Runtime state threaded through a run: the blackboard, the context window,
and the model handle. Nodes read/write the blackboard and scope system text on
the window as the tree is walked."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid an import cycle with provider
    from jdsl.provider import LanguageModel
    from jdsl.trace.events import EventSource, TraceEvent
    from jdsl.trace.sink import TraceSink


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
        # optional trace hook: RunContext installs a callback so every write can be
        # emitted as a blackboard.write event (§35 PR1) without the blackboard
        # needing to know about the trace layer. None => no capture, no overhead.
        self.on_write: Callable[[Write], None] | None = None
        for k, v in {**(initial or {}), **kwargs}.items():
            self.set(k, v, writer="input")

    def set(self, key: str, value: Any, *, writer: str = "?") -> Any:
        prev = self.get(key)
        overwrote = key in self and self._writer.get(key) not in (None, writer)
        super().__setitem__(key, value)
        self._writer[key] = writer
        record = Write(key, value, writer, prev, overwrote)
        self.activity.append(record)
        if self.on_write is not None:
            self.on_write(record)
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

    # -- trace plane (design §35 PR1) -----------------------------------------
    # A sink for canonical trace events; the default drops everything so the
    # interpreter behaves exactly as before when nobody is capturing. capture_id
    # and episode_id scope the events this run emits.
    trace_sink: TraceSink | None = None
    capture_id: str = "cap_local"
    episode_id: str = "ep_local"
    trace_source: EventSource | None = None
    _event_tail: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # accept a plain dict for convenience; upgrade it to a tracked Blackboard.
        if not isinstance(self.blackboard, Blackboard):
            self.blackboard = Blackboard(self.blackboard)
        if self.trace_sink is not None:
            self._install_trace()

    def _install_trace(self) -> None:
        from jdsl.trace.events import EventKind, EventSource

        if self.trace_source is None:
            self.trace_source = EventSource()

        def _on_write(record: Write) -> None:
            self.emit(EventKind.BLACKBOARD_WRITE, actor="system", payload={
                "key": record.key,
                "value": record.value,
                "writer": record.writer,
                "overwrote": record.overwrote,
            })

        self.blackboard.on_write = _on_write

    @property
    def tracing(self) -> bool:
        from jdsl.trace.sink import NullTraceSink
        return self.trace_sink is not None and not isinstance(self.trace_sink, NullTraceSink)

    def emit(self, kind: str, *, payload: dict[str, Any] | None = None, actor: str = "system",
             parent_event_id: str | None = None, blob_refs: list[str] | None = None) -> TraceEvent | None:
        """Emit one canonical trace event on this run's sink. No-op (returns None)
        when there is no sink. The sink assigns sequence + hash chain."""
        if self.trace_sink is None:
            return None
        from jdsl.trace.events import TraceEvent
        event = TraceEvent.new(kind, self.capture_id, self.episode_id, payload=payload,
                               actor=actor, source=self.trace_source,
                               parent_event_id=parent_event_id, blob_refs=blob_refs)
        return self.trace_sink.emit(event)

    def require_model(self) -> LanguageModel:
        if self.model is None:
            raise RuntimeError("This skill uses an LLM leaf (predict) but no model is attached. "
                               "Give the root a model, e.g. root(...).model('claude-opus-4-8').")
        return self.model
