"""P22: Metrics module (Track C) — unit tests with hand-computed values."""
from __future__ import annotations

from jdsl_harness.eval.metrics import (
    breakeven_n, pass_at_1, pass_pow_k, precision_recall, rule_of_three_upper_bound,
)


def test_pass_at_1_basic():
    assert pass_at_1([True, False, True]) == 2 / 3


def test_pass_at_1_empty():
    assert pass_at_1([]) == 0.0


def test_pass_pow_k_flat():
    assert pass_pow_k([True, False], k=1) == 0.5


def test_precision_recall_perfect():
    p, r = precision_recall([True, True], [True, True])
    assert p == 1.0 and r == 1.0


def test_precision_recall_zero_division():
    p, r = precision_recall([False, False], [True, True])
    assert p == 0.0 and r == 0.0


def test_rule_of_three_upper_bound_three():
    # With 3 successes observed, upper bound should not exceed 1
    assert rule_of_three_upper_bound(3, 10) == 1.0


def test_breakeven_positive():
    assert breakeven_n(0.8, 0.5) == 1.0


def test_breakeven_never():
    assert breakeven_n(0.1, 0.5) is None
