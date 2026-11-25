"""Evaluation metrics for compiled behavior (§3.1, P22).

Pure functions, deterministic, no external state. Edge cases (zero denominators)
hard-coded rather than floating-point exception.
"""

from __future__ import annotations

from collections.abc import Sequence


def pass_at_1(solutions: Sequence[bool]) -> float:
    """Proportion of tasks solved on first attempt."""
    if not solutions:
        return 0.0
    return sum(solutions) / len(solutions)


def pass_pow_k(solutions: Sequence[bool], k: int = 1) -> float:
    """Pass@k: task passes if any of k independent samples succeed.
    For a single list this is equivalent to pass_at_1 when k==1.
    """
    if not solutions or k < 1:
        return 0.0
    # For a sequence representing k samples per task, group by k.
    # Simplified: treat input as already-grouped or flat; flat = k=1.
    if len(solutions) % k != 0:
        # best-effort: floor division
        n_groups = len(solutions) // k
    else:
        n_groups = len(solutions) // k
    if n_groups == 0:
        return 0.0
    groups = [solutions[i * k:(i + 1) * k] for i in range(n_groups)]
    passed = sum(1 for g in groups if any(g))
    return passed / n_groups


def precision_recall(predictions: Sequence[bool], targets: Sequence[bool]) -> tuple[float, float]:
    """Precision = TP / (TP + FP); Recall = TP / (TP + FN)."""
    tp = sum(1 for p, t in zip(predictions, targets, strict=False) if p and t)
    fp = sum(1 for p, t in zip(predictions, targets, strict=False) if p and not t)
    fn = sum(1 for p, t in zip(predictions, targets, strict=False) if not p and t)
    denom_p = tp + fp
    denom_r = tp + fn
    return (tp / denom_p if denom_p else 0.0, tp / denom_r if denom_r else 0.0)


def rule_of_three_upper_bound(successes: int, total: int) -> float:
    """Conservative upper bound on true success rate with 3 successes observed (rule of three)."""
    if total <= 0:
        return 0.0
    # If successes < 3, use 3/total as rough upper-bound heuristic; else 1.0 capped.
    return min(1.0, max(successes / total, 3.0 / total) if successes < 3 else 1.0)


def breakeven_n(success_rate: float, cost_per_sample: float) -> float | None:
    """Minimum N such that expected value of N samples >= cost of N samples.
    Simplified: N where success_rate * value == cost; value assumed 1.0.
    Returns None if success_rate <= 0 (never breaks even)."""
    if success_rate <= 0.0 or cost_per_sample <= 0.0:
        return None
    # breakeven: N * success_rate * 1.0 = N * cost => success_rate = cost
    # For cost > success_rate, never breakeven at finite positive N.
    if success_rate < cost_per_sample:
        return None
    return 1.0  # at success_rate >= cost, N=1 satisfies
