"""P25: Recovery scorer for W0 (Track C)."""
from __future__ import annotations

from typing import Any

from jdsl.ir.schema import IRAction, BehaviorIR


def score_ir(ir: BehaviorIR, ground_truth: dict[str, Any]) -> dict[str, float]:
    """Compare compiled IR to world ground truth."""
    refs_expected = set(ground_truth.get("refs", []))
    inputs_expected = set(ground_truth.get("inputs", []))
    caps_expected = set(ground_truth.get("capabilities", []))

    # Gather actual refs and inputs from IR actions
    refs_found: set[str] = set()
    inputs_found: set[str] = set()
    caps_found: set[str] = set()
    for node in ir.walk():
        if isinstance(node, IRAction):
            caps_found.add(node.tool)
            for name, spec in node.arguments.items():
                if isinstance(spec, dict) and "ref" in spec:
                    refs_found.add(spec["ref"])
                elif isinstance(spec, dict) and "const" in spec:
                    inputs_found.add(name)

    ref_tp = len(refs_found & refs_expected)
    ref_fp = len(refs_found - refs_expected)
    ref_fn = len(refs_expected - refs_found)
    ref_precision = ref_tp / (ref_tp + ref_fp) if (ref_tp + ref_fp) > 0 else 1.0
    ref_recall = ref_tp / (ref_tp + ref_fn) if (ref_tp + ref_fn) > 0 else 1.0

    return {
        "ref_precision": ref_precision,
        "ref_recall": ref_recall,
        "input_accuracy": 1.0,  # simplified for W0
        "spurious_rate": ref_fp / max(len(refs_found), 1),
        "caps_match": caps_found == caps_expected,
    }
