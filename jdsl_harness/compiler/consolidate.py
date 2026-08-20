"""Cross-trace consolidation and evidence grading (design §14.2, §15, §35 PR9).

Stage B of the compiler: group equivalent local facts, measure support and
counterexamples against the episodes where each claim was *applicable*, and assign
a conservative evidence grade (§15). Frequency alone is never enough — a claim
contradicted in an applicable episode is contested and cannot become a hard rule
(§15, §44.2). Grades E4/E5 are reserved for the verifier and held-out evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jdsl_harness.compiler.candidates import (
    ACTION,
    CONTROL,
    DATAFLOW,
    RECOVERY,
    SEMANTIC,
    Fact,
    extract_facts,
)
from jdsl_harness.compiler.normalize import NormEpisode

# evidence grades (§15)
E0, E1, E2, E3, E4, E5 = "E0", "E1", "E2", "E3", "E4", "E5"


@dataclass
class Evidence:
    applicable: int = 0
    support: int = 0
    counterexamples: int = 0
    episodes: list[str] = field(default_factory=list)
    success_support: int = 0
    fail_support: int = 0


@dataclass
class Candidate:
    candidate_id: str
    type: str
    claim: dict[str, Any]
    evidence: Evidence
    grade: str = E0
    status: str = "proposed"        # proposed | contested | accepted | rejected
    contract_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id, "type": self.type, "claim": self.claim,
            "evidence": {
                "applicable": self.evidence.applicable, "support": self.evidence.support,
                "counterexamples": self.evidence.counterexamples, "episodes": self.evidence.episodes,
            },
            "grade": self.grade, "status": self.status, "contract_sources": self.contract_sources,
        }


def consolidate(episodes: list[NormEpisode], *,
                contracts: dict[tuple, list[str]] | None = None) -> list[Candidate]:
    """Consolidate local facts from all episodes into graded candidates. `contracts`
    optionally maps a fact key to contract source ids, lifting it to E3 (§15 E3)."""
    contracts = contracts or {}
    grouped: dict[tuple, list[Fact]] = {}
    for ep in episodes:
        seen_keys: set[tuple] = set()
        for fact in extract_facts(ep):
            k = fact.key()
            # count each distinct claim at most once per episode for support
            if k in seen_keys:
                continue
            seen_keys.add(k)
            grouped.setdefault(k, []).append(fact)

    candidates: list[Candidate] = []
    for i, (key, facts) in enumerate(sorted(grouped.items(), key=lambda kv: str(kv[0]))):
        rep = facts[0]
        ev = _evidence(rep, facts, episodes)
        cand = Candidate(candidate_id=f"cand_{rep.type.lower()}_{i:03d}", type=rep.type,
                         claim=rep.claim, evidence=ev)
        cand.contract_sources = contracts.get(key, [])
        cand.grade, cand.status = _grade(ev, bool(cand.contract_sources))
        candidates.append(cand)
    return candidates


def _evidence(rep: Fact, facts: list[Fact], episodes: list[NormEpisode]) -> Evidence:
    support_eps = {f.episode_id for f in facts}
    applicable_eps = {ep.episode_id for ep in episodes if _applicable(rep, ep)}
    # an applicable episode that does NOT support the claim is a counterexample (§14.2)
    counter = applicable_eps - support_eps
    by_id = {ep.episode_id: ep for ep in episodes}
    succ = sum(1 for e in support_eps if by_id[e].success)
    fail = sum(1 for e in support_eps if by_id[e].success is False)
    return Evidence(
        applicable=len(applicable_eps | support_eps), support=len(support_eps),
        counterexamples=len(counter), episodes=sorted(support_eps),
        success_support=succ, fail_support=fail,
    )


def _applicable(rep: Fact, ep: NormEpisode) -> bool:
    """Whether `rep`'s claim *could* have held in this episode (§14.2 applicability)."""
    claim = rep.claim
    tools = [s.logical_tool for s in ep.steps]
    if rep.type == DATAFLOW:
        tgt = claim["target"]
        return any(s.logical_tool == tgt["tool"] and tgt["argument"] in s.arguments for s in ep.steps)
    if rep.type == CONTROL:
        return claim["before"] in tools and claim["after"] in tools
    if rep.type == ACTION:
        return claim["tool"] in tools
    if rep.type == RECOVERY:
        return any(not s.ok and s.logical_tool == claim["on_error_of"] for s in ep.steps)
    if rep.type == SEMANTIC:
        return any(d.node_id == claim.get("node_id") for d in ep.decisions)
    return True


def _grade(ev: Evidence, contract_backed: bool) -> tuple[str, str]:
    if contract_backed:
        return E3, "accepted"
    if ev.counterexamples > 0:
        # contradicted where applicable: keep as a soft heuristic, never a hard rule
        return (E1 if ev.support >= 2 else E0), "contested"
    if ev.support >= 3:
        return E2, "accepted"
    if ev.support >= 2:
        return E1, "accepted"
    return E0, "proposed"


__all__ = ["Evidence", "Candidate", "consolidate", "E0", "E1", "E2", "E3", "E4", "E5"]
