"""Environment adapters and state observation (design §11).

Tool traces alone are not enough for good policy induction — the compiler needs
state (§11). An `EnvironmentAdapter` lets the gateway snapshot raw environment
state around mutations and read the task outcome, and canonicalizes host tool
names to logical capability ids (§11.2, §13.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

JSONValue = Any


@dataclass
class Outcome:
    """A task outcome (§11.2)."""
    reward: float | None = None
    verdict: str | None = None
    detail: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.reward is not None: out["reward"] = self.reward
        if self.verdict is not None: out["verdict"] = self.verdict
        if self.detail: out["detail"] = self.detail
        return out


@runtime_checkable
class EnvironmentAdapter(Protocol):
    """Optional environment observer (§11.2). All methods are best-effort; the
    gateway calls them only when present."""

    def snapshot(self) -> JSONValue | None: ...

    def outcome(self) -> Outcome | None: ...

    def canonical_tool(self, host_name: str) -> str: ...


class MappingEnvironment:
    """A trivial adapter: a fixed host->logical tool map and optional callables for
    snapshot/outcome. Enough for jdsl-native captures and tests."""

    def __init__(self, tool_map: dict[str, str] | None = None, *,
                 snapshot_fn: Any = None, outcome_fn: Any = None) -> None:
        self.tool_map = tool_map or {}
        self._snapshot_fn = snapshot_fn
        self._outcome_fn = outcome_fn

    def snapshot(self) -> JSONValue | None:
        return self._snapshot_fn() if self._snapshot_fn else None

    def outcome(self) -> Outcome | None:
        return self._outcome_fn() if self._outcome_fn else None

    def canonical_tool(self, host_name: str) -> str:
        return self.tool_map.get(host_name, host_name)


__all__ = ["JSONValue", "Outcome", "EnvironmentAdapter", "MappingEnvironment"]
