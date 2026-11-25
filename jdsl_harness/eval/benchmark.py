"""P26: Recovery benchmark runner, W0 only (Track C)."""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from jdsl_harness.eval.worlds import WorldW0, generate_episodes, ground_truth
from jdsl_harness.eval.oracle import OutcomeCheckerW0
from jdsl_harness.eval.scorer import score_ir
from jdsl_harness.compiler import compile_behavior
from test.conftest import FakeModel


def run_benchmark(seeds: list[int], n_episodes: int = 3) -> dict:
    results = []
    for s in seeds:
        w = WorldW0(seed=s)
        eps = generate_episodes(w, n=n_episodes)
        compiled = compile_behavior(eps, name=f"w0_s{s}")
        gt = ground_truth(w)
        score = score_ir(compiled.compiled.ir, gt)
        results.append({"seed": s, **score})
    return {"results": results, "count": len(results)}


def write_csv(results: list[dict], path: str) -> Path:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["seed", "ref_precision", "ref_recall", "spurious_rate", "caps_match"])
        for r in results:
            writer.writerow([
                r["seed"], r.get("ref_precision"), r.get("ref_recall"),
                r.get("spurious_rate"), r.get("caps_match"),
            ])
    return Path(path)
