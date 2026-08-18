# Benchmarks

Measuring jdsl against external agent benchmarks. First target: **tau-bench**
(Sierra), chosen because its `pass^k` metric scores *reliability* — the thing
jdsl's behavior tree is meant to buy — rather than one lucky trial.

## Why tau-bench

- It runs an LLM-simulated user against the agent over many turns, with domain
  tools that mutate a shared database, then grades the end state to a reward.
- `pass^k` = fraction of tasks solved on **all k** independent trials. A tree
  that removes off-policy branches should shed fewer trials as `k` grows.
- Its tasks and data ship **inside its git repo** — no separate dataset
  download.

## Setup

tau-bench is a sibling install, not vendored here (keeps its license separate
and updates trivial):

```bash
git clone https://github.com/sierra-research/tau-bench
cd tau-bench && pip install -e .
```

Keys: the agent side uses jdsl's usual keys (`ANTHROPIC_API_KEY` /
`DEEPSEEK_API_KEY` / `OPENAI_API_KEY`). tau-bench *also* runs an LLM
user-simulator — point it at a cheap model (`--user-model gpt-4o-mini`, or a
DeepSeek model) since it needn't be the smart half. Every episode is therefore
two model streams.

## Run

From the jdsl repo, with tau-bench importable:

```bash
# Arm A — model-steered baseline (policy in the prompt)
python -m bench.tau_bench_adapter --env retail --arm flat \
    --agent-model claude-opus-4-8 --user-model gpt-4o-mini \
    --tasks 0,1,2 --k 5

# Arm B — tree-steered (policy in seq/sel/check guards)
python -m bench.tau_bench_adapter --env retail --arm tree \
    --tree-module bench.retail_policy \
    --tasks 0,1,2 --k 5
```

Output is per-task rewards, the average, and the strict `pass^k` verdict, plus a
final `pass^k on N/M tasks` line. The **experiment** is running both arms over
the same tasks and comparing those `pass^k` rates.

## The two arms

| Arm | Flag | Where policy lives | Status |
| --- | ---- | ------------------ | ------ |
| Model-steered | `--arm flat` | The system prompt (`env.wiki`) | Wired end-to-end |
| Tree-steered | `--arm tree --tree-module M` | `seq`/`sel`/`check` guards in a jdsl tree | You supply `M.build_tree(tools, wiki)` |

The tree is the domain-modeling work — and the actual research contribution.
`M.build_tree(tools, wiki)` receives the wrapped tau-bench tools and the domain
policy text and returns a jdsl `Node` that:

- reads the incoming user turn from blackboard key `user_message`,
- gates privileged tool actions behind `check(...)` guards on blackboard state
  that earlier turns set (authentication, order ownership, cancellation
  windows),
- writes the reply to the user to blackboard key `reply`.

State persists across turns because the `Session` reuses one blackboard for the
whole episode — see `test/test_session.py::test_tree_gates_state_across_turns`
for the shape in miniature.

## How it maps onto jdsl

`jdsl/session.py` adds `Session`, the multi-turn primitive `Root.run()` isn't:
one persistent `RunContext` (blackboard + window + model) driven turn by turn
via `send(user_message) -> reply`. `bench/tau_bench_adapter.py` wraps each
tau-bench tool as a jdsl `Tool` bridging to `env.step`, and alternates
`session.send(...)` with tau-bench's `respond` action to fetch the next
simulated-user turn.

Everything jdsl-side is offline-tested with the `FakeModel` used across the
suite (`test/test_session.py`); only the adapter itself needs a live tau-bench +
keys.

## Roadmap

- [ ] Land a `bench/retail_policy.py` reference tree for Arm B.
- [ ] BFCL smoke test of the `react`/`Session` function-calling layer (cheaper,
      single-turn) before spending on full tau-bench runs.
- [ ] airline domain (harder policy) once retail is solid.
