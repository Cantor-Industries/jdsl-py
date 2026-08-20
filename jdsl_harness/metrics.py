"""Package + experiment metrics (design §33, §34).

Final pass rate is necessary but not sufficient (§33). These functions compute the
metrics that make the jdsl thesis measurable from a compiled package alone —
residual decision burden, deterministic coverage, active policy tokens, visible
tool branching factor, and exact dataflow rate — plus a helper to summarize an A/E
experiment table (§34.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jdsl.ir.schema import (
    BehaviorIR,
    IRAction,
    IRGuard,
    IRGuardCall,
    IRPredict,
    IRReact,
    Signature,
)

_MODEL_TYPES = (IRPredict, IRReact)
_DETERMINISTIC_TYPES = (IRAction, IRGuard, IRGuardCall)


@dataclass
class PackageMetrics:
    meaningful_decisions: int
    model_dependent_decisions: int
    residual_decision_burden: float
    deterministic_coverage: float
    active_policy_tokens: float          # avg instruction tokens per model leaf
    visible_tool_branching_factor: float  # avg tools exposed per model decision
    exact_dataflow_rate: float           # fraction of args supplied by refs

    def to_dict(self) -> dict[str, Any]:
        return {
            "meaningful_decisions": self.meaningful_decisions,
            "model_dependent_decisions": self.model_dependent_decisions,
            "residual_decision_burden": self.residual_decision_burden,
            "deterministic_coverage": self.deterministic_coverage,
            "active_policy_tokens": self.active_policy_tokens,
            "visible_tool_branching_factor": self.visible_tool_branching_factor,
            "exact_dataflow_rate": self.exact_dataflow_rate,
        }


def package_metrics(ir: BehaviorIR) -> PackageMetrics:
    nodes = ir.walk()
    model_nodes = [n for n in nodes if isinstance(n, _MODEL_TYPES)]
    det_nodes = [n for n in nodes if isinstance(n, _DETERMINISTIC_TYPES)]
    total = len(model_nodes) + len(det_nodes)

    sigs = [ir.signatures.get(n.signature) for n in model_nodes]
    sigs = [s for s in sigs if s is not None]
    tokens = [_instruction_tokens(s) for s in sigs]
    branching = [len(s.tools) for s in sigs]

    ref_args, all_args = 0, 0
    for n in nodes:
        if isinstance(n, IRAction):
            for spec in n.arguments.values():
                all_args += 1
                if isinstance(spec, dict) and "ref" in spec:
                    ref_args += 1

    return PackageMetrics(
        meaningful_decisions=total,
        model_dependent_decisions=len(model_nodes),
        residual_decision_burden=_ratio(len(model_nodes), total),
        deterministic_coverage=_ratio(len(det_nodes), total),
        active_policy_tokens=round(sum(tokens) / len(tokens), 2) if tokens else 0.0,
        visible_tool_branching_factor=round(sum(branching) / len(branching), 2) if branching else 0.0,
        exact_dataflow_rate=_ratio(ref_args, all_args),
    )


@dataclass
class ArmResult:
    """One experimental arm's outcome (§34.2)."""
    name: str
    pass_rate: float
    active_policy_tokens: float = 0.0
    tool_branching_factor: float = 0.0
    residual_decision_burden: float = 0.0


def compare_arms(arms: list[ArmResult]) -> dict[str, Any]:
    """Summarize an A/E comparison table and check the §34.4 success criteria:
    the compiled package should beat both the raw agent and the text-Skill arm
    while lowering active tokens, branching, and residual burden."""
    by_name = {a.name.lower(): a for a in arms}
    compiled = _find(by_name, "compil", "jdsl")
    raw = _find(by_name, "raw")
    skill = _find(by_name, "skill", "text")
    criteria: dict[str, Any] = {}
    if compiled and raw:
        criteria["beats_raw"] = compiled.pass_rate > raw.pass_rate
    if compiled and skill:
        criteria["beats_text_skill"] = compiled.pass_rate > skill.pass_rate
        criteria["lower_active_tokens"] = compiled.active_policy_tokens <= skill.active_policy_tokens
        criteria["lower_branching"] = compiled.tool_branching_factor <= skill.tool_branching_factor
    return {"arms": [a.__dict__ for a in arms], "criteria": criteria,
            "success": all(criteria.values()) if criteria else None}


def _instruction_tokens(sig: Signature) -> int:
    return len((sig.instruction or "").split())


def _ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _find(by_name: dict[str, ArmResult], *needles: str) -> ArmResult | None:
    for name, arm in by_name.items():
        if any(n in name for n in needles):
            return arm
    return None


__all__ = ["PackageMetrics", "package_metrics", "ArmResult", "compare_arms"]
