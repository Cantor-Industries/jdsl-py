"""Residualize the semantic decisions the compiler could not remove (design §18,
§26, §35 PR10).

Everything the staticizer can prove deterministic has been lowered to control,
dataflow, guards, and fixed actions. What remains — genuine language judgment — is
turned into typed residual signatures (§18): the small interface between one tree
leaf and the frozen model. A residual leaf prefers `predict` + deterministic `act`
over a wide-open `react` (§18.3).
"""

from __future__ import annotations

from jdsl.ir.schema import IRPredict, IRReact, Signature
from jdsl_harness.compiler.model import CompilerModel, HeuristicCompilerModel
from jdsl_harness.compiler.normalize import ModelDecision


def residualize_decision(decision: ModelDecision, *, model: CompilerModel | None = None,
                         ) -> tuple[Signature, IRPredict | IRReact]:
    """Turn one observed model decision into a typed Signature + its IR leaf."""
    model = model or HeuristicCompilerModel()
    payload = {"node_id": decision.node_id, "inputs": decision.inputs,
               "outputs": decision.outputs, "kind": decision.kind}
    sig = model.name_signature(payload)
    node_id = decision.node_id or sig.id
    if sig.kind == "react":
        return sig, IRReact(type="react", id=node_id, signature=sig.id)
    return sig, IRPredict(type="predict", id=node_id, signature=sig.id)


__all__ = ["residualize_decision"]
