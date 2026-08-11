"""Single-child decorators: invert, optional, timeout, oneshot."""

from __future__ import annotations

import time

from jdsl import RunContext, Status, act, check, invert, oneshot, optional, repeat, root, seq, timeout


def test_invert_flips_status():
    assert invert(check("k", 1)).tick(RunContext(blackboard={"k": 1})) is Status.FAILURE
    assert invert(check("k", 1)).tick(RunContext(blackboard={"k": 2})) is Status.SUCCESS


def test_optional_always_succeeds_but_runs_child():
    calls: list[int] = []

    def boom() -> Status:
        calls.append(1)
        return Status.FAILURE

    assert optional(act(boom)).tick(RunContext()) is Status.SUCCESS
    assert calls == [1]  # the child still ran


def test_optional_does_not_abort_a_sequence():
    reached: list[str] = []
    root("S").do(
        seq(
            optional(act(lambda: Status.FAILURE)),  # would normally fail-fast the seq
            act(lambda: reached.append("after")),
        )
    ).run()
    assert reached == ["after"]  # optional shielded the failure


def test_timeout_fails_when_child_overruns():
    slow = act(lambda: time.sleep(0.5))
    assert timeout(slow, seconds=0.05).tick(RunContext()) is Status.FAILURE


def test_timeout_passes_when_child_is_quick():
    assert timeout(act(lambda: None), seconds=1.0).tick(RunContext()) is Status.SUCCESS


def test_oneshot_runs_child_once_and_replays_status():
    calls: list[int] = []

    def once() -> Status:
        calls.append(1)
        return Status.SUCCESS

    node = oneshot(act(once))
    ctx = RunContext()
    assert node.tick(ctx) is Status.SUCCESS
    assert node.tick(ctx) is Status.SUCCESS  # replayed, not re-run
    assert calls == [1]


def test_oneshot_state_is_per_run():
    calls: list[int] = []
    node = oneshot(act(lambda: calls.append(1)))
    node.tick(RunContext())
    node.tick(RunContext())  # a fresh context -> runs again
    assert calls == [1, 1]


def test_oneshot_inside_repeat_runs_child_once():
    calls: list[int] = []
    node = repeat(oneshot(act(lambda: calls.append(1))), max=5)
    assert node.tick(RunContext()) is Status.SUCCESS
    assert calls == [1]  # 5 loop passes, but the child fired only once
