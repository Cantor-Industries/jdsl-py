"""Behavior candidate mining — the six atom types (design §4.2, §14.1, §16, §35 PR9).

Stage A of the compiler (§14.1): analyze each normalized episode independently and
extract *local* behavior facts — no generalization yet. Facts carry a grouping key
so `consolidate.py` (Stage B) can measure support and counterexamples across many
episodes and assign an evidence grade (§15).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jdsl_harness.compiler.normalize import NormEpisode

# the six behavior atom types (§4.2)
CONTROL = "CONTROL"
DATAFLOW = "DATAFLOW"
GUARD = "GUARD"
ACTION = "ACTION"
RECOVERY = "RECOVERY"
SEMANTIC = "SEMANTIC"


@dataclass
class Fact:
    """One local behavior observation from a single episode."""
    type: str
    claim: dict[str, Any]
    episode_id: str
    outcome_ok: bool | None = None
    state_before: dict[str, Any] = field(default_factory=dict)

    def key(self) -> tuple:
        """Stable identity for grouping equivalent facts across episodes."""
        return (self.type, _freeze(self.claim))


def extract_facts(ep: NormEpisode) -> list[Fact]:
    """All local facts from one normalized episode (§14.1)."""
    facts: list[Fact] = []
    facts += _dataflow_facts(ep)
    facts += _control_facts(ep)
    facts += _action_facts(ep)
    facts += _recovery_facts(ep)
    facts += _semantic_facts(ep)
    return facts


def _dataflow_facts(ep: NormEpisode) -> list[Fact]:
    """Exact value movement (§16.1): each argument sourced from a prior state path."""
    out: list[Fact] = []
    for step in ep.steps:
        for arg, path in step.arg_lineage.items():
            if path:
                out.append(Fact(DATAFLOW, {
                    "source": path,
                    "target": {"tool": step.logical_tool, "argument": arg},
                }, ep.episode_id, ep.success))
    return out


def _control_facts(ep: NormEpisode) -> list[Fact]:
    """Ordering: each adjacent successful (A precedes B) pair (§16.2)."""
    out: list[Fact] = []
    ok_steps = [s for s in ep.steps if s.ok]
    for a, b in zip(ok_steps, ok_steps[1:], strict=False):
        out.append(Fact(CONTROL, {"before": a.logical_tool, "after": b.logical_tool},
                        ep.episode_id, ep.success))
    return out


def _action_facts(ep: NormEpisode) -> list[Fact]:
    """A tool operation performed (§16.4). The claim keeps the argument *lineage*
    shape (which args are refs) so staticization can build a fixed act."""
    out: list[Fact] = []
    for step in ep.steps:
        if step.ok:
            out.append(Fact(ACTION, {
                "tool": step.logical_tool,
                "store": step.store,
                "ref_args": sorted(k for k, v in step.arg_lineage.items() if v),
                "arg_paths": {k: v for k, v in step.arg_lineage.items() if v},
            }, ep.episode_id, ep.success))
    return out


def _recovery_facts(ep: NormEpisode) -> list[Fact]:
    """A failure-to-recovery relation (§16.5): a failed step followed by a
    different successful step."""
    out: list[Fact] = []
    for a, b in zip(ep.steps, ep.steps[1:], strict=False):
        if not a.ok and b.ok and b.logical_tool != a.logical_tool:
            out.append(Fact(RECOVERY, {
                "on_error_of": a.logical_tool,
                "error_class": _error_class(a.error),
                "recover_with": b.logical_tool,
            }, ep.episode_id, ep.success))
    return out


def _semantic_facts(ep: NormEpisode) -> list[Fact]:
    """Residual semantic decisions observed (§16.6)."""
    out: list[Fact] = []
    for d in ep.decisions:
        out.append(Fact(SEMANTIC, {
            "kind": d.kind,
            "inputs": sorted(d.inputs),
            "outputs": sorted(d.outputs),
            "node_id": d.node_id,
        }, ep.episode_id, ep.success))
    return out


def _error_class(error: Any) -> str:
    text = str(error or "").lower()
    for token in ("not_found", "not found", "unauthorized", "invalid", "timeout", "rate", "forbidden"):
        if token in text:
            return token.replace(" ", "_")
    return "error"


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


__all__ = ["Fact", "extract_facts", "CONTROL", "DATAFLOW", "GUARD", "ACTION", "RECOVERY", "SEMANTIC"]
