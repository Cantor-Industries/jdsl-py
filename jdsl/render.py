"""Render a skill's structure as an ASCII tree — for the CLI and for debugging.

Every node advertises a `label()` and its `_children()` (each an (edge, node)
pair); we just walk them. No execution, no model — pure structure.
"""

from __future__ import annotations

from jdsl.tree import Node


def render(node: Node) -> str:
    """An ASCII-tree rendering of `node` and its descendants."""
    lines = [_label(node)]
    _walk(node, "", lines)
    return "\n".join(lines)


def _label(node: Node) -> str:
    """A node's label, suffixed with its stable author id (§20) when it has one,
    so `jdsl show` reveals the ids a compiled package refers to."""
    return node.label() + (f"  #{node.node_id}" if node.node_id else "")


def _walk(node: Node, prefix: str, lines: list[str]) -> None:
    children = node._children()
    for i, (edge, child) in enumerate(children):
        last = i == len(children) - 1
        connector = "└─ " if last else "├─ "
        tag = f"{edge}: " if edge else ""
        lines.append(f"{prefix}{connector}{tag}{_label(child)}")
        _walk(child, prefix + ("   " if last else "│  "), lines)


__all__ = ["render"]
