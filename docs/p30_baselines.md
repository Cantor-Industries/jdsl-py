# P30: Recovery baselines for W0, W1 and W2 (Track C)

Produced by the offline, deterministic runner in `jdsl_harness/eval/benchmark.py`:

```python
from jdsl_harness.eval.benchmark import run_benchmark, summarise
summarise(run_benchmark([1, 2, 3], n_episodes=3, worlds=["w0", "w1", "w2"])["results"])
```

Same config → same rows (verified: `run_benchmark([1,2], ...)` is byte-identical
across runs). Times are well under a second per config.

## Results (seeds 1,2,3; n=3 episodes)

| World | compile OK | replay cov. | ref precision | ref recall | spurious | caps match | residual recovered | guard recovered |
|-------|-----------|-------------|---------------|-----------|----------|------------|--------------------|-----------------|
| W0 (linear chain) | ✅ | 1.0 | 1.0 | 1.0 | 0.0 | ✅ | n/a | n/a |
| W1 (residual decision) | ✅ | 1.0 | 1.0 | 1.0 | 0.0 | ✅ | **1.0** | n/a |
| W2 (policy guard) | ✅ | 1.0 | 1.0 | 1.0 | 0.0 | ✅ | n/a | **0.0** |

`residual_recovered` = the compiled IR contains the planted residual signature
(`resolve_target`). `guard_recovered` = the compiled IR contains an `IRGuard`
node. These are reported separately because the ref metrics alone do **not**
prove a residual or a guard was learned.

## Reading the numbers

- **W0/W1 refs are fully recovered.** The earlier "~0.67 precision" figure was a
  scorer bug: it counted the free input `email` as a spurious dataflow ref. Free
  inputs are supplied at run time and are now excluded (P25).
- **W1 residual is recovered** as a model leaf with the planted signature; its
  deciding feature is recorded in `ground_truth(WorldW1(...))["residual"]`.
- **W2 guard is not recovered (0.0).** The compiler still emits the guarded
  action unconditionally: no `IRGuard` is produced for a conditionally-taken
  action (defect D2, repro `test_d2_no_learned_guards`). This is the expected
  poor baseline that Track D (P37/P38) exists to improve. The W2 ref metrics are
  therefore *not* evidence of guard learning.
- **Coincidence traps (P27)** are labelled `not a ref` in ground truth; the
  scorer counts a compiled ref into a trap slot as spurious even when the value
  matches. See `test/test_world_options.py`.
