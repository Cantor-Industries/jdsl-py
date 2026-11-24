"""Reproduction tests for suspected defects (evaluation plan §2).

Each test targets one suspicion. Expected today: most fail for the stated
reason and are marked xfail(strict=True).  If a test passes, the suspicion
was wrong — delete the xfail and record it as "not reproduced."

No behavior changes here: tests and fixtures only.
"""

from __future__ import annotations

import pytest

from jdsl import act, root, store
from jdsl.context import RunContext
from jdsl.package import export_jdsl, load_package
from jdsl.trace import ListTraceSink, segment_episodes
from jdsl.tree import Status
from jdsl_harness.compiler import compile_behavior
from test.conftest import FakeModel

# ---------------------------------------------------------------------------
# P02: D8 — positional args dropped in compiled actions
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "D8 [suspected]: _build_action skips _argN keys, so positional arguments "
    "are dropped from compiled actions."
))
def test_d8_positional_args_survive_compilation(tmp_path):
    """A tool called with a positional arg: compile and run; the tool must
    receive the argument."""

    received = {}

    def my_tool(value):
        received["value"] = value
        return {"ok": True}

    # build episodes with a positional arg via act(fn, "x")
    sink = ListTraceSink()
    for i in range(3):
        val = f"item_{i}"
        skill = root("pos").do(store(act(my_tool, val), "result"))
        skill.run(trace_sink=sink, model=FakeModel("0"), episode_id=f"ep_{i}",
                  capture_id="cap_pos")
    episodes = segment_episodes(sink.events)

    result = compile_behavior(episodes, name="pos-test")
    loaded = load_package(export_jdsl(result.package, tmp_path / "pos_test"))

    # run the compiled package — the tool should get a value argument
    received.clear()
    bound = loaded.as_root({"my_tool": my_tool})
    ctx = RunContext(blackboard={}, model=FakeModel("0"))
    status = bound.tick(ctx)
    assert status is Status.SUCCESS
    assert "value" in received, "positional argument was not passed to the tool"
