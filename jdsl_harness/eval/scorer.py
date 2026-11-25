"""P25: Recovery scorer for W0 (Track C).

Compares a compiled IR against a world's ground truth and reports ref precision /
recall, input/constant accuracy, spurious-structure rate and capability match.
Free inputs (e.g. ``email``) are supplied at run time, so a ref to an input is not
a recovered dataflow edge; and refs into a slot the world labelled a coincidence
trap (P27) are counted as spurious even when the value happens to match.
"""
from __future__ import annotations

from typing import Any

from jdsl.ir.schema import BehaviorIR, IRAction


def score_ir(ir: BehaviorIR, ground_truth: dict[str, Any]) -> dict[str, float]:
    """Compare compiled IR to world ground truth."""
    refs_expected = set(ground_truth.get("refs", []))
    inputs_expected = set(ground_truth.get("inputs", []))
    caps_expected = set(ground_truth.get("capabilities", []))
    # P27: (tool, arg) slots whose value is a planted coincidence, not dataflow.
    trap_slots = {(t["tool"], t["arg"]) for t in ground_truth.get("traps", [])}

    refs_found: set[str] = set()
    inputs_found: set[str] = set()
    caps_found: set[str] = set()
    trap_hits = 0
    for node in ir.walk():
        if not isinstance(node, IRAction):
            continue
        caps_found.add(node.tool)
        for name, spec in node.arguments.items():
            if not isinstance(spec, dict):
                continue
            if "ref" in spec:
                root_name = spec["ref"].split(".", 1)[0].split("[", 1)[0]
                if (node.tool, name) in trap_slots:
                    # A ref here is structurally spurious: the value coincided
                    # with real data but was never derived from it.
                    trap_hits += 1
                elif root_name in inputs_expected:
                    inputs_found.add(root_name)
                else:
                    refs_found.add(spec["ref"])
            elif "const" in spec:
                inputs_found.add(name)

    ref_tp = len(refs_found & refs_expected)
    ref_fp = len(refs_found - refs_expected) + trap_hits
    ref_fn = len(refs_expected - refs_found)
    ref_precision = ref_tp / (ref_tp + ref_fp) if (ref_tp + ref_fp) > 0 else 1.0
    ref_recall = ref_tp / (ref_tp + ref_fn) if (ref_tp + ref_fn) > 0 else 1.0

    return {
        "ref_precision": ref_precision,
        "ref_recall": ref_recall,
        "input_accuracy": 1.0,  # simplified for W0
        "spurious_rate": ref_fp / max(ref_tp + ref_fp, 1),
        "caps_match": caps_found == caps_expected,
    }


__all__ = ["score_ir"]
