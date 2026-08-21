"""Staticization: build the Behavior IR from evidence (design §17, §25, §35 PR11).

The compiler objective is lowest model burden while preserving verified behavior
(§17, §2.3). We follow the staticization ordering (§17): constant? exact dataflow?
deterministic predicate? fixed action? bounded recovery? classification? — and only
what survives as genuine judgment stays a residual model leaf.

The structural method is §25: build a control skeleton from the modal successful
trajectory, replace instance values with refs, insert verified guards, wrap known
recovery, and residualize the rest.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from jdsl.ir.schema import (
    BehaviorIR,
    IRAction,
    IRGuard,
    IRNode,
    IRSelector,
    IRSequence,
    Signature,
)
from jdsl.package.manifest import NodeProvenance
from jdsl_harness.compiler.candidates import ACTION, DATAFLOW, GUARD, RECOVERY
from jdsl_harness.compiler.consolidate import E1, E3, E4, Candidate
from jdsl_harness.compiler.model import CompilerModel, HeuristicCompilerModel
from jdsl_harness.compiler.normalize import NormEpisode, NormStep, synth_node_id, synth_store
from jdsl_harness.compiler.residualize import residualize_decision

_ACCEPTED_DATAFLOW = {E1, "E2", E3, E4}


@dataclass
class CompiledBehavior:
    """The staticizer's output: an IR, its provenance, and burden metrics (§33)."""
    ir: BehaviorIR
    provenance: list[NodeProvenance] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    required_capabilities: list[str] = field(default_factory=list)


def staticize(episodes: list[NormEpisode], candidates: list[Candidate], *,
              name: str = "behavior", model: CompilerModel | None = None,
              compiler_model_id: str | None = None) -> CompiledBehavior:
    model = model or HeuristicCompilerModel()
    skeleton = _pick_skeleton(episodes)
    if skeleton is None:
        empty = BehaviorIR(root=IRSequence(type="sequence", id=f"{name}_flow", children_=[]))
        return CompiledBehavior(ir=empty, stats={"note": "no successful episode to compile"})

    dataflow = _index_dataflow(candidates)
    recovery = _index_recovery(candidates)
    guards = _index_guards(candidates)
    inputs = _input_args(episodes, dataflow)

    children: list[IRNode] = []
    signatures: dict[str, Signature] = {}
    provenance: list[NodeProvenance] = []
    caps: set[str] = set()
    decisions_by_index = _decisions_by_index(skeleton)

    n_deterministic = 0
    n_model = 0

    for i, step in enumerate(skeleton.steps):
        # interleave residual decisions observed just before this step
        for decision in decisions_by_index.get(i, []):
            sig, leaf = residualize_decision(decision, model=model)
            signatures[sig.id] = sig
            children.append(leaf)
            provenance.append(NodeProvenance(node_id=leaf.id or sig.id, evidence_grade="E0",
                                             behavior_candidate=None, compiler_model=compiler_model_id,
                                             rationale_summary="residual semantic decision"))
            n_model += 1
            caps.update(sig.tools)

        # a verified guard scoped before this tool (§16.3)
        for gcand in guards.get(step.logical_tool, []):
            gnode = IRGuard(type="guard", id=f"guard_{step.logical_tool}_{i}".replace(".", "_"),
                            expression=gcand.claim["expression"])
            children.append(gnode)
            provenance.append(_prov(gnode.id, gcand, compiler_model_id))
            n_deterministic += 1

        action = _build_action(step, i, dataflow, inputs, caps)
        acand = _action_candidate(candidates, step)
        prov = _prov(action.id, acand, compiler_model_id) if acand else NodeProvenance(
            node_id=action.id or "", evidence_grade="E0", compiler_model=compiler_model_id)

        # known bounded recovery -> sel(action, recovery) (§16.5)
        rcand = recovery.get(step.logical_tool)
        if rcand is not None:
            rec_tool = rcand.claim["recover_with"]
            caps.add(rec_tool)
            recover = IRAction(type="action", id=f"recover_{i}", tool=rec_tool,
                               store=action.store)
            node: IRNode = IRSelector(type="selector", id=f"try_{action.id}",
                                      children_=[action, recover])
            provenance.append(_prov(node.id, rcand, compiler_model_id))
        else:
            node = action
        provenance.append(prov)
        children.append(node)
        n_deterministic += 1

    # any trailing decisions after the last step
    for decision in decisions_by_index.get(len(skeleton.steps), []):
        sig, leaf = residualize_decision(decision, model=model)
        signatures[sig.id] = sig
        children.append(leaf)
        provenance.append(NodeProvenance(node_id=leaf.id or sig.id, evidence_grade="E0",
                                         compiler_model=compiler_model_id,
                                         rationale_summary="residual semantic decision"))
        n_model += 1
        caps.update(sig.tools)

    root = IRSequence(type="sequence", id=f"{name}_flow", children_=children)
    ir = BehaviorIR(root=root, signatures=signatures)
    total = n_deterministic + n_model
    declared_inputs = sorted({arg for (_tool, arg) in inputs})
    stats = {
        "meaningful_decisions": total,
        "model_dependent_decisions": n_model,
        "residual_decision_burden": round(n_model / total, 4) if total else 0.0,
        "deterministic_coverage": round(n_deterministic / total, 4) if total else 0.0,
        "exact_dataflow_refs": sum(1 for s in skeleton.steps for v in s.arg_lineage.values() if v),
        "inputs": declared_inputs,
    }
    return CompiledBehavior(ir=ir, provenance=provenance, stats=stats,
                            required_capabilities=sorted(caps))


# -- skeleton + indexing ------------------------------------------------------

def _pick_skeleton(episodes: list[NormEpisode]) -> NormEpisode | None:
    """The representative trajectory: the modal successful tool sequence (§25.1).
    Falls back to any episode if none is marked successful."""
    successful = [e for e in episodes if e.success] or episodes
    if not successful:
        return None
    seqs = Counter(tuple(e.tool_sequence()) for e in successful)
    modal = seqs.most_common(1)[0][0]
    return next(e for e in successful if tuple(e.tool_sequence()) == modal)


def _decisions_by_index(ep: NormEpisode) -> dict[int, list]:
    out: dict[int, list] = {}
    for d in ep.decisions:
        out.setdefault(d.index, []).append(d)
    return out


def _index_dataflow(candidates: list[Candidate]) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for c in candidates:
        if c.type == DATAFLOW and c.grade in _ACCEPTED_DATAFLOW and c.status != "rejected":
            tgt = c.claim["target"]
            out[(tgt["tool"], tgt["argument"])] = c.claim["source"]
    return out


def _index_recovery(candidates: list[Candidate]) -> dict[str, Candidate]:
    out: dict[str, Candidate] = {}
    for c in candidates:
        if c.type == RECOVERY and c.grade in {E1, "E2", E3, E4} and c.status == "accepted":
            out.setdefault(c.claim["on_error_of"], c)
    return out


def _index_guards(candidates: list[Candidate]) -> dict[str, list[Candidate]]:
    out: dict[str, list[Candidate]] = {}
    for c in candidates:
        # hard guards require contract-backed / verified evidence (§15, §32.3)
        if c.type == GUARD and c.grade in {E3, E4} and "before_tool" in c.claim:
            out.setdefault(c.claim["before_tool"], []).append(c)
    return out


def _action_candidate(candidates: list[Candidate], step: NormStep) -> Candidate | None:
    for c in candidates:
        if c.type == ACTION and c.claim.get("tool") == step.logical_tool:
            return c
    return None


def _build_action(step: NormStep, i: int, dataflow: dict[tuple[str, str], str],
                  inputs: set[tuple[str, str]], caps: set[str]) -> IRAction:
    caps.add(step.logical_tool)
    arguments: dict[str, Any] = {}
    for arg, value in step.arguments.items():
        if arg.startswith("_arg"):
            continue  # positional placeholder; keep kwargs only in compiled form
        path = dataflow.get((step.logical_tool, arg)) or step.arg_lineage.get(arg)
        if path:
            arguments[arg] = {"ref": path}          # verified exact dataflow (§16.1)
        elif (step.logical_tool, arg) in inputs:
            arguments[arg] = {"ref": arg}            # free input: bound from run seed (§17)
        else:
            arguments[arg] = {"const": value}        # constant across all episodes
    store = step.store or synth_store(step.logical_tool, i)
    node_id = step.node_id or synth_node_id(step.logical_tool, i)
    return IRAction(type="action", id=node_id, tool=step.logical_tool,
                    arguments=arguments, store=store)


def _input_args(episodes: list[NormEpisode],
                dataflow: dict[tuple[str, str], str]) -> set[tuple[str, str]]:
    """A (tool, arg) is a free *input*, not a constant, when it has no verified
    dataflow source yet its value is not identical across every episode that
    supplies it (§17: "constant?" is only satisfied by an invariant value). Such
    args compile to a ref bound from the run's seeded inputs."""
    seen: dict[tuple[str, str], set[str]] = {}
    for ep in episodes:
        for step in ep.steps:
            for arg, value in step.arguments.items():
                if arg.startswith("_arg"):
                    continue
                key = (step.logical_tool, arg)
                if key in dataflow or step.arg_lineage.get(arg):
                    continue  # explained by dataflow — never an input
                seen.setdefault(key, set()).add(_stable(value))
    return {key for key, values in seen.items() if len(values) > 1}


def _stable(value: Any) -> str:
    import json
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        return repr(value)


def _prov(node_id: str | None, cand: Candidate, compiler_model_id: str | None) -> NodeProvenance:
    return NodeProvenance(
        node_id=node_id or "", behavior_candidate=cand.candidate_id, evidence_grade=cand.grade,
        source_episodes=cand.evidence.episodes, contract_sources=cand.contract_sources,
        compiler_model=compiler_model_id,
        rationale_summary=f"{cand.type} candidate, support={cand.evidence.support}, "
                          f"counterexamples={cand.evidence.counterexamples}",
    )


__all__ = ["CompiledBehavior", "staticize"]
