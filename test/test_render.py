"""The ASCII-tree renderer."""

from __future__ import annotations

from jdsl import act, check, invert, predict, render, repeat, root, sel, seq, tool


def test_renders_nested_structure():
    skill = root("Triage", system="x").model("deepseek-chat").do(
        seq(
            predict("message -> category"),
            sel(
                seq(check("category", "billing"), act(lambda: None)),
                invert(check("category", "spam")),
            ),
        )
    )
    out = render(skill)
    lines = out.splitlines()
    assert lines[0] == "root 'Triage' [deepseek-chat]"
    assert "predict(message -> category)" in out
    assert "check(category == 'billing')" in out
    assert "invert" in out
    # last child of the root uses the └─ connector, earlier ones ├─
    assert "└─ seq" in out
    assert "├─ predict(message -> category)" in out


def test_repeat_until_edge_is_labelled():
    skill = root("R").do(repeat(predict("d -> ok"), until=check("ok", "yes"), max=2))
    out = render(skill)
    assert "repeat(max=2)" in out
    assert "until: check(ok == 'yes')" in out


def test_leaf_renders_as_single_line():
    @tool
    def greet(name: str) -> None: ...
    assert render(act(greet, "x")) == "act(greet)"
