"""The compiler model — a hypothesis generator, not the final authority
(design §24.1, §38, §53 principle 3).

The frontier model proposes abstractions (semantic groupings, candidate guards,
residual wording); recorded evidence, schemas, and replay decide what survives
(§24.1). This module defines the role interface and a fully offline
`HeuristicCompilerModel` so the whole pipeline runs deterministically in tests and
CI (§46). `LLMCompilerModel` plugs a real `jdsl.LanguageModel` into the same
interface with structured (JSON) output.

Nothing here is ever trusted for exact dataflow, guard truth, support counts, or
package integrity (§24.1) — those stay deterministic in the other modules.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from jdsl.ir.schema import Signature, SignatureInput, SignatureOutput


class CompilerModel(Protocol):
    """The roles the compiler model plays (§38). Each returns structured data the
    deterministic pipeline then verifies."""

    def name_signature(self, decision: dict[str, Any]) -> Signature: ...

    def propose_guard(self, context: dict[str, Any]) -> dict[str, Any] | None: ...

    def word_instruction(self, signature: Signature, samples: list[dict[str, Any]]) -> str: ...


class HeuristicCompilerModel:
    """Deterministic, offline stand-in (§46 CI). Produces reasonable signatures and
    wording from the structure alone — no network, stable output."""

    def name_signature(self, decision: dict[str, Any]) -> Signature:
        node_id = decision.get("node_id") or "residual_decision"
        inputs = decision.get("inputs") or []
        outputs = decision.get("outputs") or ["answer"]
        kind = decision.get("kind", "predict")
        output_name = outputs[0]
        sig = Signature(
            id=str(node_id), kind=kind,
            inputs={name: SignatureInput(source=name) for name in inputs},
            output=SignatureOutput(name=output_name, schema=_infer_schema(output_name)),
            tools=decision.get("tools", []),
            context_policy={"include_only": list(inputs)},
        )
        sig.instruction = self.word_instruction(sig, [])
        return sig

    def propose_guard(self, context: dict[str, Any]) -> dict[str, Any] | None:
        """A contrastive guard proposal from positive/negative state sets (§16.3).
        The heuristic finds a single field that is constant across positives and
        never takes that value in negatives, and proposes an equality guard. The
        deterministic verifier decides whether the evidence actually supports it."""
        positives: list[dict[str, Any]] = context.get("positive_states", [])
        negatives: list[dict[str, Any]] = context.get("negative_states", [])
        if not positives:
            return None
        common = _common_fields(positives)
        for field_, value in sorted(common.items()):
            if all(_get(n, field_) != value for n in negatives):
                return {"eq": [{"ref": field_}, value]}
        return None

    def word_instruction(self, signature: Signature, samples: list[dict[str, Any]]) -> str:
        out = signature.output.name if signature.output else "result"
        ins = ", ".join(signature.inputs) or "the context"
        verb = _verb_for(out)
        return f"{verb} the {out.replace('_', ' ')} from {ins}. Respond with only the {out}."


class LLMCompilerModel:
    """Wraps a real `jdsl.LanguageModel` behind the same interface, asking for JSON
    and validating it. Falls back to the heuristic on any parse/validation failure,
    so a flaky model never corrupts a package."""

    def __init__(self, model: Any, *, model_id: str | None = None) -> None:
        self.model = model
        self.model_id = model_id
        self._fallback = HeuristicCompilerModel()

    def name_signature(self, decision: dict[str, Any]) -> Signature:
        return self._fallback.name_signature(decision)

    def propose_guard(self, context: dict[str, Any]) -> dict[str, Any] | None:
        return self._fallback.propose_guard(context)

    def word_instruction(self, signature: Signature, samples: list[dict[str, Any]]) -> str:
        prompt = (
            "Write ONE concise imperative instruction (max 25 words) for a small model.\n"
            f"Inputs: {list(signature.inputs)}\n"
            f"Output: {signature.output.name if signature.output else 'answer'} "
            f"({(signature.output.schema if signature.output else {})})\n"
            "Return JSON: {\"instruction\": \"...\"}. No prose."
        )
        try:
            text = self.model.generate(system="", messages=[{"role": "user", "content": prompt}],
                                       model_id=self.model_id)
            data = json.loads(_extract_json(text))
            instr = str(data["instruction"]).strip()
            if instr:
                return instr
        except Exception:  # noqa: BLE001 — never let the model break compilation
            pass
        return self._fallback.word_instruction(signature, samples)


# -- helpers ------------------------------------------------------------------

def _infer_schema(output_name: str) -> dict[str, Any]:
    low = output_name.lower()
    if any(t in low for t in ("index", "count", "number", "_id_num")):
        return {"type": "integer", "minimum": 0}
    if any(t in low for t in ("is_", "has_", "confirmed", "flag")):
        return {"type": "boolean"}
    return {"type": "string"}


def _verb_for(output_name: str) -> str:
    low = output_name.lower()
    if "index" in low or "select" in low or "target" in low:
        return "Choose"
    if "intent" in low or "category" in low or "class" in low:
        return "Classify"
    if "confirm" in low:
        return "Determine"
    return "Produce"


def _common_fields(states: list[dict[str, Any]]) -> dict[str, Any]:
    flat = [_flatten(s) for s in states]
    if not flat:
        return {}
    common: dict[str, Any] = {}
    for field_, value in flat[0].items():
        if all(other.get(field_, _MISS) == value for other in flat[1:]):
            common[field_] = value
    return common


_MISS = object()


def _flatten(state: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in state.items():
        path = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, path))
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[path] = v
    return out


def _get(state: dict[str, Any], path: str) -> Any:
    cur: Any = state
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISS
    return cur


def _extract_json(text: str) -> str:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start >= 0 and end > start else text


__all__ = ["CompilerModel", "HeuristicCompilerModel", "LLMCompilerModel"]
