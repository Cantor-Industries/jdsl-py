"""P26/P30: Recovery benchmark runner for W0, W1 (residual) and W2 (guard).

For each seed and world it generates episodes, compiles them, scores the compiled
IR against the world ground truth, and returns one row per (world, seed). The
runner is offline and deterministic: the same config always yields the same rows.
"""
from __future__ import annotations

import csv
from pathlib import Path

from jdsl.ir.schema import IRGuard, IRPredict
from jdsl_harness.compiler import compile_behavior
from jdsl_harness.eval.scorer import score_ir
from jdsl_harness.eval.worlds import (
    WorldW0,
    WorldW1,
    WorldW2,
    generate_episodes,
    ground_truth,
)

WORLDS = {"w0": WorldW0, "w1": WorldW1, "w2": WorldW2}
_FIELDS = ["world", "seed", "compile_ok", "replay_coverage",
           "ref_precision", "ref_recall", "spurious_rate", "caps_match",
           "residual_recovered", "guard_recovered"]


def run_benchmark(seeds: list[int], n_episodes: int = 3,
                  worlds: list[str] | None = None) -> dict:
    """Compile and score every (world, seed); return rows plus a summary."""
    rows = []
    for key in (worlds or ["w0"]):
        cls = WORLDS[key]
        for s in seeds:
            world = cls(seed=s)
            episodes = generate_episodes(world, n=n_episodes)
            compiled = compile_behavior(episodes, name=f"{key}_s{s}")
            gt = ground_truth(world)
            nodes = compiled.compiled.ir.walk()
            score = score_ir(compiled.compiled.ir, gt)
            rows.append({
                "world": key,
                "seed": s,
                "compile_ok": compiled.verification.ok,
                "replay_coverage": compiled.verification.replay_coverage,
                **score,
                # P30: the ref metrics above do not measure whether the residual
                # decision or the guard predicate was actually recovered.
                "residual_recovered": _residual_recovered(nodes, gt),
                "guard_recovered": _guard_recovered(nodes, gt),
            })
    return {"results": rows, "count": len(rows)}


def _residual_recovered(nodes: list, gt: dict) -> bool | None:
    residual = gt.get("residual")
    if not residual:
        return None
    return any(isinstance(n, IRPredict) and n.signature == residual["signature"]
               for n in nodes)


def _guard_recovered(nodes: list, gt: dict) -> bool | None:
    if not gt.get("guard"):
        return None
    return any(isinstance(n, IRGuard) for n in nodes)


def summarise(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Mean of each metric per world, for the committed results note."""
    acc: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        bucket = acc.setdefault(row["world"], {})
        for field in _FIELDS[2:]:
            value = row.get(field)
            if isinstance(value, bool):
                value = 1.0 if value else 0.0
            if value is None:
                continue
            bucket.setdefault(field, []).append(float(value))
    return {
        world: {field: sum(vals) / len(vals) for field, vals in metrics.items()}
        for world, metrics in acc.items()
    }


def write_csv(results: list[dict], path: str) -> Path:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_FIELDS)
        for r in results:
            writer.writerow([r.get(field) for field in _FIELDS])
    return Path(path)


__all__ = ["run_benchmark", "summarise", "write_csv", "WORLDS"]
