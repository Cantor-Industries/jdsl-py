"""Verification: deterministic layers that decide what survives (design §32, §35 PR12).

Compilation without verification produces fragile policies (§32). None of this
trusts the compiler model — every check is deterministic (§24.1): structural
validity (§32.1), then replay of the compiled deterministic behavior against the
historical episodes (§32.2). Dataflow refs that reproduce the recorded values, and
guards that pick the recorded branch, are promoted to replay-verified (E4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jdsl.ir.expr import _MISSING as EXPR_MISSING
from jdsl.ir.expr import evaluate, resolve_path
from jdsl.ir.schema import IRAction, IRGuard
from jdsl.ir.validate import validate_ir
from jdsl_harness.compiler.consolidate import E4
from jdsl_harness.compiler.normalize import NormEpisode
from jdsl_harness.compiler.staticize import CompiledBehavior


@dataclass
class VerificationReport:
    structural_ok: bool = True
    structural_problems: list[str] = field(default_factory=list)
    replay_checks: int = 0
    replay_passed: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def replay_coverage(self) -> float:
        return round(self.replay_passed / self.replay_checks, 4) if self.replay_checks else 1.0

    @property
    def ok(self) -> bool:
        return self.structural_ok and not self.problems and self.replay_passed == self.replay_checks

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "passed" if self.ok else "failed",
            "structural_ok": self.structural_ok,
            "replay_coverage": self.replay_coverage,
            "replay_checks": self.replay_checks,
            "replay_passed": self.replay_passed,
            "problems": self.structural_problems + self.problems,
        }


def verify(compiled: CompiledBehavior, episodes: list[NormEpisode], *,
           required_capabilities: set[str] | None = None) -> VerificationReport:
    report = VerificationReport()

    structural = validate_ir(compiled.ir, required_capabilities=required_capabilities)
    report.structural_ok = structural.ok
    report.structural_problems = list(structural.problems)

    _replay(compiled, episodes, report)
    return report


def _replay(compiled: CompiledBehavior, episodes: list[NormEpisode],
            report: VerificationReport) -> None:
    """Replay deterministic refs and guards against each episode's reconstructed
    state (§32.2). A ref must resolve to the value the episode actually used; a
    guard must hold in the states where its action fired."""
    actions = {n.id: n for n in compiled.ir.walk() if isinstance(n, IRAction)}
    guards = [n for n in compiled.ir.walk() if isinstance(n, IRGuard)]

    for ep in episodes:
        # dataflow: each compiled ref must resolve, in the step's recorded state,
        # to the value the episode actually used (§32.2).
        for step in ep.steps:
            node = actions.get(step.node_id) or actions.get(_synth_id(step))
            if node is None:
                continue
            for arg, value in step.arguments.items():
                spec = node.arguments.get(arg)
                if not (isinstance(spec, dict) and "ref" in spec):
                    continue
                report.replay_checks += 1
                resolved = resolve_path(spec["ref"], step.state_before)
                if resolved is EXPR_MISSING or resolved != value:
                    report.problems.append(
                        f"replay {ep.episode_id}: ref {spec['ref']!r} for "
                        f"{step.logical_tool}.{arg} resolved to {resolved!r} != recorded {value!r}")
                else:
                    report.replay_passed += 1

        # guards: evaluate against the last recorded state; a guard false in a
        # successful episode is a real problem, otherwise it correctly gated a failure.
        final_state = ep.steps[-1].state_before if ep.steps else {}
        for guard in guards:
            report.replay_checks += 1
            try:
                held = evaluate(guard.expression, final_state)
            except Exception as e:  # noqa: BLE001
                report.problems.append(f"replay {ep.episode_id}: guard {guard.id!r} error: {e}")
                continue
            if held or not ep.success:
                report.replay_passed += 1
            else:
                report.problems.append(
                    f"replay {ep.episode_id}: guard {guard.id!r} false in a successful episode")


def promote_replay_verified(compiled: CompiledBehavior, report: VerificationReport) -> None:
    """When replay is fully clean, lift each compiled node's provenance to E4
    (replay-verified, §15). Safety-sensitive guards still needed E3 to be compiled."""
    if report.ok and report.replay_checks > 0:
        for prov in compiled.provenance:
            if prov.evidence_grade in ("E1", "E2"):
                prov.evidence_grade = E4


def _synth_id(step) -> str:
    from jdsl_harness.compiler.staticize import _slug
    return f"{_slug(step.logical_tool)}_{step.index}"


__all__ = ["VerificationReport", "verify", "promote_replay_verified"]
