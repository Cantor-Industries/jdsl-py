"""jdsl-harness: capture, storage, host adapters, and the behavior compiler
(design §6.1, §36). Kept as a separate package so the dependency-light `jdsl`
runtime core stays small (§36) — the compiler and adapters live here."""

from jdsl_harness.compiler import compile_behavior
from jdsl_harness.metrics import ArmResult, PackageMetrics, compare_arms, package_metrics

__all__ = ["compile_behavior", "package_metrics", "PackageMetrics", "ArmResult", "compare_arms"]
