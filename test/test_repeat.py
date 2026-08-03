"""The repeat/retry decorator."""

from __future__ import annotations

from jdsl import RunContext, Status, act, check, repeat, root, sel, store


def test_stops_early_when_until_succeeds():
    counter = iter([1, 2, 3])
    node = repeat(store(act(lambda: next(counter)), "n"), until=check("n", 2), max=5)
    ctx = RunContext()
    assert node.tick(ctx) is Status.SUCCESS
    assert ctx.blackboard["n"] == 2  # stopped on the 2nd pass


def test_fails_when_until_never_met():
    counter = iter(range(100))
    node = repeat(store(act(lambda: next(counter)), "n"), until=check("n", 999), max=3)
    ctx = RunContext()
    assert node.tick(ctx) is Status.FAILURE
    assert ctx.blackboard["n"] == 2  # ran exactly max=3 times (0,1,2)


def test_without_until_runs_max_times_then_succeeds():
    calls: list[int] = []
    node = repeat(act(lambda: calls.append(1)), max=4)
    assert node.tick(RunContext()) is Status.SUCCESS
    assert len(calls) == 4


def test_aborts_on_child_failure():
    calls: list[int] = []

    def once() -> Status:
        calls.append(1)
        return Status.FAILURE

    node = repeat(act(once), until=check("x", 1), max=5)
    assert node.tick(RunContext()) is Status.FAILURE
    assert len(calls) == 1  # aborted after the first failing pass


def test_failure_triggers_selector_fallback():
    hit: list[str] = []
    counter = iter(range(10))
    root("S").do(
        sel(
            repeat(store(act(lambda: next(counter)), "n"), until=check("n", 999), max=2),
            act(lambda: hit.append("fallback")),
        )
    ).run()
    assert hit == ["fallback"]  # repeat FAILUREd -> selector fell through
