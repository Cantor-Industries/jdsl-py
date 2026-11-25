# P30: Benchmark W0 and W1/W2 baselines (Track C)

Baseline from `run_benchmark(seeds=[1,2,3], n_episodes=3)` on W0 (current master, P12–P22 applied):

- `ref_precision`: ~1.0 (planted dataflow refs recovered correctly)
- `ref_recall`: ~1.0
- `spurious_rate`: 0.0 (no false refs after P16/P17 evidence floor)
- `caps_match`: True

Expected poor on W1 (residual decision) and W2 (guard) today because compiler does not yet compile residual model leaves or verified guards at full coverage. Numbers should improve after P08/P09 fixes land.
