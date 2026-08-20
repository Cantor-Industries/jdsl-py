"""Deterministic trajectory normalization (design §13, §35 PR8).

Raw traces carry surface variation; the compiler needs symbolic structure. This
stage turns a canonical `Episode` into a `NormEpisode`: an ordered list of action
steps whose arguments are annotated with exact dataflow lineage (§16.1) and whose
instance-specific values are replaced with symbolic references (§13.2). No model
is used — every decision here is structural and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jdsl.trace.events import EventKind
from jdsl.trace.replay import Episode
from jdsl_harness.compiler.lineage import find_source


@dataclass
class NormStep:
    """One normalized action step (a tool call) with lineage-annotated arguments."""
    index: int
    logical_tool: str
    host_tool: str | None
    arguments: dict[str, Any]
    arg_lineage: dict[str, str | None]      # argname -> ref path in prior state, or None
    result: Any = None
    ok: bool = True
    error: Any = None
    store: str | None = None
    node_id: str | None = None
    state_before: dict[str, Any] = field(default_factory=dict)  # trusted state at call time

    def symbolic_args(self) -> dict[str, Any]:
        """Arguments with lineaged values replaced by `$ref(path)` markers (§13.2)."""
        out: dict[str, Any] = {}
        for k, v in self.arguments.items():
            path = self.arg_lineage.get(k)
            out[k] = {"ref": path} if path else {"const": v}
        return out


@dataclass
class ModelDecision:
    """A residual semantic decision observed in the trace (react/predict leaf)."""
    index: int
    node_id: str | None
    inputs: list[str]
    outputs: list[str]
    kind: str = "predict"           # predict | react


@dataclass
class NormEpisode:
    episode_id: str
    steps: list[NormStep] = field(default_factory=list)
    decisions: list[ModelDecision] = field(default_factory=list)
    success: bool | None = None
    outcome: dict[str, Any] | None = None
    source_digest: str | None = None    # last event hash: a stable episode fingerprint

    def tool_sequence(self) -> list[str]:
        return [s.logical_tool for s in self.steps]


def normalize_episode(episode: Episode, *, canonical: dict[str, str] | None = None) -> NormEpisode:
    """Normalize one episode. `canonical` maps host tool names to logical ids
    (§13.1 tool canonicalization); unmapped tools keep their host name."""
    canonical = canonical or {}
    norm = NormEpisode(episode_id=episode.episode_id)
    env: dict[str, Any] = {}          # cumulative trusted state before the current step
    pending: dict[str, NormStep] = {}  # started tool calls awaiting result, by event id
    index = 0

    for e in episode.ordered():
        if e.kind == EventKind.BLACKBOARD_WRITE:
            env[e.payload["key"]] = e.payload.get("value")
        elif e.kind == EventKind.TOOL_CALL_STARTED:
            tool = e.payload.get("tool", {})
            host = tool.get("host_name")
            logical = tool.get("logical_id") or canonical.get(host or "", host or "unknown")
            arguments = dict(e.payload.get("arguments", {}) or {})
            import copy
            lineage = {k: find_source(v, env) for k, v in arguments.items()}
            step = NormStep(index=index, logical_tool=logical, host_tool=host,
                            arguments=arguments, arg_lineage=lineage,
                            store=e.payload.get("store"), node_id=e.payload.get("node_id"),
                            state_before=copy.deepcopy(env))
            norm.steps.append(step)
            pending[e.event_id] = step
            index += 1
        elif e.kind == EventKind.TOOL_CALL_COMPLETED:
            step = pending.get(e.parent_event_id or "") or (norm.steps[-1] if norm.steps else None)
            if step is not None:
                step.result = e.payload.get("result")
                # register the result under its store name so later steps can
                # reference it (the symbolic $var of §13.2); also feed env.
                name = e.payload.get("store") or step.store
                if name:
                    env[name] = step.result
        elif e.kind == EventKind.TOOL_CALL_FAILED:
            step = pending.get(e.parent_event_id or "") or (norm.steps[-1] if norm.steps else None)
            if step is not None:
                step.ok = False
                step.error = e.payload.get("error")
        elif e.kind == EventKind.REACT_STARTED:
            norm.decisions.append(ModelDecision(
                index=index, node_id=e.payload.get("node_id"),
                inputs=e.payload.get("inputs", []), outputs=e.payload.get("outputs", []), kind="react"))
        elif e.kind == EventKind.NODE_ENTER and e.payload.get("type") == "predict":
            ins, outs = _parse_predict_label(e.payload.get("label", ""))
            norm.decisions.append(ModelDecision(
                index=index, node_id=e.payload.get("node_id"), inputs=ins, outputs=outs, kind="predict"))
        elif e.kind in (EventKind.ENVIRONMENT_REWARD, EventKind.ENVIRONMENT_VERDICT):
            norm.outcome = e.payload

    norm.success = episode.succeeded()
    ordered = episode.ordered()
    norm.source_digest = ordered[-1].event_hash if ordered else None
    return norm


def _parse_predict_label(label: str) -> tuple[list[str], list[str]]:
    """Parse a predict label `predict(a, b -> c)` into (inputs, outputs)."""
    inner = label[label.find("(") + 1:label.rfind(")")] if "(" in label else ""
    if "->" not in inner:
        return [], []
    lhs, rhs = inner.split("->", 1)
    ins = [s.strip() for s in lhs.split(",") if s.strip()]
    outs = [s.strip() for s in rhs.split(",") if s.strip()]
    return ins, outs


def normalize_all(episodes: list[Episode], *, canonical: dict[str, str] | None = None) -> list[NormEpisode]:
    return [normalize_episode(e, canonical=canonical) for e in episodes]


__all__ = ["NormStep", "ModelDecision", "NormEpisode", "normalize_episode", "normalize_all"]
