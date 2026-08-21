"""Assemble a portable BehaviorPackage from compiled + verified behavior
(design §22, §23, §35 PR13) and the end-to-end compile pipeline (§24).

`compile_behavior` is the whole spine (§24): normalize → consolidate → staticize →
verify → package. It is deterministic given the traces and the (optional) compiler
model; the model only proposes wording/signatures, never the structure or the
evidence counts (§24.1).
"""

from __future__ import annotations

from typing import Any

from jdsl.package.export import BehaviorPackage
from jdsl.package.manifest import Manifest, ToolContract, ToolEffects
from jdsl.trace.replay import Episode
from jdsl_harness.compiler.consolidate import Candidate, consolidate
from jdsl_harness.compiler.model import CompilerModel
from jdsl_harness.compiler.normalize import NormEpisode, normalize_all
from jdsl_harness.compiler.staticize import CompiledBehavior, staticize
from jdsl_harness.compiler.verify import VerificationReport, promote_replay_verified, verify


def compile_behavior(episodes: list[Episode], *, name: str = "behavior",
                     task_family: str = "", canonical: dict[str, str] | None = None,
                     contracts: dict[tuple, list[str]] | None = None,
                     effects: dict[str, ToolEffects] | None = None,
                     model: CompilerModel | None = None, compiler_model_id: str | None = None,
                     capture_fidelity: str = "F3", version: str = "0.1.0") -> CompileResult:
    """Run the whole compiler pipeline over canonical trace episodes (§24)."""
    norm = normalize_all(episodes, canonical=canonical)
    candidates = consolidate(norm, contracts=contracts)
    compiled = staticize(norm, candidates, name=name, model=model, compiler_model_id=compiler_model_id)
    report = verify(compiled, norm, required_capabilities=set(compiled.required_capabilities))
    promote_replay_verified(compiled, report)
    pkg = build_package(compiled, report, candidates, norm, name=name, task_family=task_family,
                        effects=effects, compiler_model_id=compiler_model_id,
                        capture_fidelity=capture_fidelity, version=version)
    return CompileResult(package=pkg, compiled=compiled, candidates=candidates,
                         verification=report, normalized=norm)


class CompileResult:
    """The full output of one compile run — package plus every intermediate."""

    def __init__(self, *, package: BehaviorPackage, compiled: CompiledBehavior,
                 candidates: list[Candidate], verification: VerificationReport,
                 normalized: list[NormEpisode]) -> None:
        self.package = package
        self.compiled = compiled
        self.candidates = candidates
        self.verification = verification
        self.normalized = normalized

    def report(self) -> dict[str, Any]:
        return {
            "name": self.package.manifest.name,
            "verification": self.verification.to_dict(),
            "stats": self.compiled.stats,
            "candidates": len(self.candidates),
            "required_capabilities": self.package.manifest.required_capabilities,
        }


def build_package(compiled: CompiledBehavior, report: VerificationReport,
                  candidates: list[Candidate], norm: list[NormEpisode], *,
                  name: str, task_family: str = "", effects: dict[str, ToolEffects] | None = None,
                  compiler_model_id: str | None = None, capture_fidelity: str = "F3",
                  version: str = "0.1.0") -> BehaviorPackage:
    effects = effects or {}
    caps = compiled.required_capabilities
    tools = [ToolContract(logical_id=c, effects=effects.get(c, ToolEffects())) for c in caps]

    manifest = Manifest(
        name=name, version=version, task_family=task_family, required_capabilities=list(caps),
        source={"compiler": "jdsl-compiler", "compiler_model": compiler_model_id,
                "capture_fidelity": capture_fidelity, "episode_count": len(norm),
                "inputs": compiled.stats.get("inputs", [])},
        verification=report.to_dict(),
    )
    evidence_summary = {
        "episode_count": len(norm),
        "successful": sum(1 for e in norm if e.success),
        "candidates_by_grade": _by_grade(candidates),
        "candidates_by_type": _by_type(candidates),
        "residual_decision_burden": compiled.stats.get("residual_decision_burden"),
        "deterministic_coverage": compiled.stats.get("deterministic_coverage"),
    }
    tests = {
        "replay": [{"episode": e.episode_id, "success": e.success,
                    "source_digest": e.source_digest} for e in norm],
        "guards": [c.to_dict() for c in candidates if c.type == "GUARD"],
        "signatures": [{"id": sid, **sig.to_dict()} for sid, sig in compiled.ir.signatures.items()],
    }
    return BehaviorPackage(
        manifest=manifest, ir=compiled.ir, tools=tools, provenance=compiled.provenance,
        tests=tests, evidence_summary=evidence_summary,
        invariants=[c.to_dict() for c in candidates if c.grade == "E3" and c.type == "GUARD"],
    )


def _by_grade(candidates: list[Candidate]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in candidates:
        out[c.grade] = out.get(c.grade, 0) + 1
    return out


def _by_type(candidates: list[Candidate]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in candidates:
        out[c.type] = out.get(c.type, 0) + 1
    return out


__all__ = ["compile_behavior", "CompileResult", "build_package"]
