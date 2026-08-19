"""Run jdsl agents against tau-bench (Sierra's tool-agent reliability benchmark).

tau-bench is NOT vendored here. Install it as a sibling from its own repo:

    git clone https://github.com/sierra-research/tau-bench
    cd tau-bench && pip install -e .

then run this adapter from the jdsl repo with tau-bench importable on the path.

What this does
--------------
tau-bench drives an LLM-simulated user against your agent over many turns; the
agent calls domain tools that mutate a shared database, and at the end the final
DB state + what the agent told the user are graded to a reward in {0, 1}. Its
headline metric is pass^k — did the agent succeed on *all k* independent trials
of a task — which is a reliability/determinism score, exactly what jdsl's tree
is meant to buy.

We wrap each tau-bench tool as a jdsl `Tool` (bridging to `env.step`) and drive
the episode with a jdsl `Session`. Two arms, to make the determinism claim
measurable rather than asserted:

* ``--arm flat`` : one model-steered Session (policy in the system prompt). The
  baseline every framework submits. Fully wired here.
* ``--arm tree`` : a tree-steered Session where domain policy lives in
  ``seq``/``sel``/``check`` guards. The tree itself is domain-specific work —
  supply it via ``--tree-module mymod`` exposing ``build_tree(tools, wiki)``.

The gap between the two arms' pass^k is the experiment.

NOTE ON VERSIONS: tau-bench's internal module paths have moved between releases.
The imports below target the current `sierra-research/tau-bench` layout; if your
installed version differs, adjust `_load_tau_bench` — every call into tau-bench
is funnelled through the small shim there so there is exactly one place to fix.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jdsl import Session
from jdsl.dsl import Tool
from jdsl.provider import LanguageModel

# -- tau-bench shim: the only place that imports tau-bench --------------------

@dataclass
class _TauBench:
    get_env: Callable[..., Any]
    Action: Callable[..., Any]
    respond_action_name: str


def _load_tau_bench() -> _TauBench:
    try:
        from tau_bench.envs import get_env  # type: ignore
        from tau_bench.types import Action  # type: ignore
    except ImportError as err:  # pragma: no cover - depends on external install
        raise SystemExit(
            "tau-bench is not importable. Install it:\n"
            "    pip install 'git+https://github.com/sierra-research/tau-bench.git'\n"
            f"(underlying import error: {err})"
        ) from err
    # RESPOND_ACTION_NAME lives in tau_bench.envs.base in current releases; fall
    # back to the documented literal if the constant moves again.
    respond = "respond"
    try:
        from tau_bench.envs.base import RESPOND_ACTION_NAME  # type: ignore
        respond = RESPOND_ACTION_NAME
    except Exception:  # pragma: no cover
        pass
    return _TauBench(get_env=get_env, Action=Action, respond_action_name=respond)


# -- wrapping tau-bench tools as jdsl tools -----------------------------------

def build_tools(tb: _TauBench, env: Any) -> list[Tool]:
    """One jdsl Tool per tau-bench tool, each bridging to `env.step`.

    tau-bench exposes tools as OpenAI-style specs on `env.tools_info`; we reuse
    that JSON schema verbatim (via Tool.parameters) instead of re-deriving it,
    and route every call through `env.step(Action(name, kwargs))`, returning the
    observation string the environment produces.
    """
    tools: list[Tool] = []
    for spec in env.tools_info:
        fn_spec = spec["function"] if "function" in spec else spec
        name = fn_spec["name"]
        tools.append(Tool(
            fn=_env_tool(tb, env, name),
            name=name,
            description=fn_spec.get("description", ""),
            parameters=fn_spec.get("parameters", {"type": "object", "properties": {}}),
        ))
    return tools


def _env_tool(tb: _TauBench, env: Any, name: str) -> Callable[..., str]:
    def call(**kwargs: Any) -> str:
        resp = env.step(tb.Action(name=name, kwargs=kwargs))
        return str(resp.observation)
    call.__name__ = name
    return call


# -- one episode --------------------------------------------------------------

def run_episode(
    tb: _TauBench,
    env: Any,
    task_index: int,
    *,
    agent_model_id: str,
    model: LanguageModel,
    build_tree: Callable[[list[Tool], str], Any] | None = None,
    max_turns: int = 30,
) -> float:
    """Run one task to completion; return its reward (typically 0.0 or 1.0)."""
    reset = env.reset(task_index=task_index)
    user_msg = _observation(reset)
    tools = build_tools(tb, env)
    wiki = getattr(env, "wiki", "")

    if build_tree is not None:
        session = Session(model=model, model_id=agent_model_id, system=wiki,
                          tree=build_tree(tools, wiki))
    else:
        session = Session(model=model, model_id=agent_model_id, system=wiki, tools=tools)

    reward, done, turns = 0.0, False, 0
    while not done and turns < max_turns:
        reply = session.send(user_msg)
        resp = env.step(tb.Action(name=tb.respond_action_name, kwargs={"content": reply}))
        user_msg = _observation(resp)
        reward = float(getattr(resp, "reward", 0.0) or 0.0)
        done = bool(getattr(resp, "done", False))
        turns += 1
    return reward


def _observation(resp: Any) -> str:
    obs = getattr(resp, "observation", resp)
    return obs if isinstance(obs, str) else str(obs)


# -- pass^k reliability metric ------------------------------------------------

def pass_hat_k(rewards: list[float], threshold: float = 0.999) -> bool:
    """True iff every trial cleared the reward threshold — the strict all-k-pass
    reading of pass^k. (tau-bench also ships an unbiased estimator over n>k
    trials; this simple form is enough to compare the two arms.)"""
    return bool(rewards) and all(r >= threshold for r in rewards)


def run_task_k(
    tb: _TauBench,
    env_factory: Callable[[], Any],
    task_index: int,
    *,
    k: int,
    **episode_kwargs: Any,
) -> list[float]:
    """Run one task k independent times (fresh env each trial); return rewards."""
    rewards: list[float] = []
    for _ in range(k):
        env = env_factory()  # fresh DB state per trial
        rewards.append(run_episode(tb, env, task_index, **episode_kwargs))
    return rewards


# -- CLI ----------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run jdsl agents against tau-bench.")
    p.add_argument("--env", default="retail", help="tau-bench domain (retail | airline)")
    p.add_argument("--agent-model", default="claude-opus-4-8", help="jdsl agent model id")
    p.add_argument("--user-model", default="gpt-4o-mini", help="tau-bench user-simulator model")
    p.add_argument("--user-provider", default="openai")
    p.add_argument("--task-split", default="test")
    p.add_argument("--tasks", default="0", help="comma-separated task indices, e.g. 0,1,2")
    p.add_argument("--k", type=int, default=1, help="trials per task (pass^k)")
    p.add_argument("--arm", choices=["flat", "tree"], default="flat")
    p.add_argument("--tree-module", default=None,
                   help="module exposing build_tree(tools, wiki) -> Node, required for --arm tree")
    p.add_argument("--max-turns", type=int, default=30)
    args = p.parse_args(argv)

    tb = _load_tau_bench()
    model = LanguageModel.from_config()

    build_tree = None
    if args.arm == "tree":
        if not args.tree_module:
            p.error("--arm tree requires --tree-module exposing build_tree(tools, wiki)")
        build_tree = importlib.import_module(args.tree_module).build_tree

    def env_factory() -> Any:
        return tb.get_env(args.env, user_strategy="llm", user_model=args.user_model,
                          user_provider=args.user_provider, task_split=args.task_split)

    task_indices = [int(t) for t in args.tasks.split(",") if t.strip()]
    episode_kwargs = dict(agent_model_id=args.agent_model, model=model,
                          build_tree=build_tree, max_turns=args.max_turns)

    passed = 0
    for task_index in task_indices:
        rewards = run_task_k(tb, env_factory, task_index, k=args.k, **episode_kwargs)
        ok = pass_hat_k(rewards)
        passed += ok
        avg = sum(rewards) / len(rewards)
        print(f"task {task_index:>3}  arm={args.arm}  rewards={rewards}  "
              f"avg={avg:.2f}  pass^{args.k}={'Y' if ok else 'N'}")

    n = len(task_indices)
    print(f"\n{args.arm}: pass^{args.k} on {passed}/{n} tasks  ({passed / n:.1%})" if n else "no tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
