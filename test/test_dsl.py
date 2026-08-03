"""The authoring surface: tools, combinators, signatures, refs."""

from __future__ import annotations

import pytest

from jdsl import act, check, predict, ref, root, sel, seq, store, tool
from jdsl.context import Ref
from jdsl.dsl import Tool, _parse_signature
from jdsl.tree import Action, Check, Predict, Root, Selector, Sequence


def test_tool_bare_decorator_is_callable_with_metadata():
    @tool
    def greet(name: str) -> str:
        """Say hi."""
        return f"hi {name}"

    assert isinstance(greet, Tool)
    assert greet("bob") == "hi bob"
    assert greet.name == "greet"
    assert greet.description == "Say hi."


def test_tool_with_explicit_name_and_description():
    @tool(name="search", description="find things")
    def f(q: str) -> list[str]:
        return [q]

    assert f.name == "search" and f.description == "find things"
    assert f("x") == ["x"]


def test_combinators_build_expected_node_types():
    assert isinstance(seq(), Sequence)
    assert isinstance(sel(), Selector)
    assert isinstance(act(lambda: None), Action)
    assert isinstance(check("k", 1), Check)
    assert isinstance(predict("a -> b"), Predict)
    assert isinstance(root("R"), Root)


def test_act_binds_literal_args_and_kwargs():
    node = act(lambda a, b=0: None, 1, b=2)
    assert node.args == (1,) and node.kwargs == {"b": 2}


def test_ref_is_a_placeholder():
    r = ref("query")
    assert isinstance(r, Ref) and r.name == "query"


def test_store_sets_store_as_and_returns_same_node():
    a = act(lambda: 1)
    assert store(a, "k") is a
    assert a.store_as == "k"


def test_root_builder_chaining():
    r = root("R", system="sys").model("claude-opus-4-8").do(seq())
    assert r.name == "R" and r.model_id == "claude-opus-4-8"
    assert isinstance(r.child, Sequence)
    assert r.context_system == "sys"


@pytest.mark.parametrize(
    "sig,expected",
    [
        ("a -> b", (("a",), ("b",))),
        ("a, b -> c", (("a", "b"), ("c",))),
        ("question -> answer, confidence", (("question",), ("answer", "confidence"))),
        ("  x ,y ->  z ", (("x", "y"), ("z",))),
    ],
)
def test_signature_parsing(sig, expected):
    assert _parse_signature(sig) == expected


@pytest.mark.parametrize("bad", ["no arrow", "a -> ", "-> ", "a, b"])
def test_signature_parsing_rejects_bad(bad):
    with pytest.raises(ValueError):
        _parse_signature(bad)
