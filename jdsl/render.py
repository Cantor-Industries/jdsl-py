"""Render a skill's structure as an ASCII tree — for the CLI and for debugging.

Every node advertises a `label()` and its `_children()` (each an (edge, node)
pair); we just walk them. No execution, no model — pure structure.
"""

from __future__ import annotations

from jdsl.tree import Node


def render(node: Node) -> str:
    """An ASCII-tree rendering of `node` and its descendants."""
    lines = [node.label()]
    _walk(node, "", lines)
    return "\n".join(lines)


def _walk(node: Node, prefix: str, lines: list[str]) -> None:
    children = node._children()
    for i, (edge, child) in enumerate(children):
        last = i == len(children) - 1
        connector = "└─ " if last else "├─ "
        tag = f"{edge}: " if edge else ""
        lines.append(f"{prefix}{connector}{tag}{child.label()}")
        _walk(child, prefix + ("   " if last else "│  "), lines)


__all__ = ["render"]
