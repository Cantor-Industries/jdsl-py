"""Exact dataflow lineage (design §16.1, §13.2).

The single most valuable deterministic signal: when a tool argument value is
*exactly* a value that already exists in trusted state, the model should not
regenerate it — it should reference it (§16.1 "If the identifier already exists in
trusted state, the model should not regenerate the identifier"). This module finds,
for a given value, the JSON path in a prior state that produced it. No model
involved; this is pure structural comparison.
"""

from __future__ import annotations

from typing import Any

# values too trivial to treat as meaningful lineage (spurious-match risk, §44.1)
_TRIVIAL = (None, True, False, "", 0, 1, -1)


def is_meaningful(value: Any) -> bool:
    """Only mine lineage for identifier-like values: non-trivial scalars. Strings
    must be at least 2 chars; small ints/bools are too common to attribute."""
    if value in _TRIVIAL:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return len(value) >= 2
    if isinstance(value, int):
        return abs(value) > 1
    if isinstance(value, float):
        return True
    return False


def find_source(value: Any, state: dict[str, Any], *, max_depth: int = 6) -> str | None:
    """Return the best JSON path in `state` whose value equals `value` exactly, or
    None. Paths use dotted keys and `[i]` indices (the ref syntax of §21.1). A list
    index equal to a state variable is emitted symbolically (`orders[$selected_index]`,
    §49) so it generalizes to the model's decision rather than hardcoding the row."""
    if not is_meaningful(value):
        return None
    paths = find_all_sources(value, state, max_depth=max_depth)
    return paths[0] if paths else None


def find_all_sources(value: Any, state: dict[str, Any], *, max_depth: int = 6) -> list[str]:
    """Every path in `state` equal to `value`. Ordered best-first: symbolic-index
    paths (which generalize) before literal-index paths, then shortest."""
    if not is_meaningful(value):
        return []
    index_names = _index_names(state)
    found: list[str] = []
    for key, sub in state.items():
        found.extend(_search(sub, str(key), value, max_depth, index_names))
    # prefer generalizing ($) paths, then shorter ones; stable for determinism
    return sorted(set(found), key=lambda p: (p.count("$") == 0, len(p), p))


def _index_names(state: dict[str, Any]) -> dict[int, str]:
    """Top-level state keys holding a small non-negative int (or digit string) —
    candidate symbolic array indices (e.g. selected_index=1 -> `$selected_index`).
    A digit string counts because an untyped teacher `predict` stores its choice as
    text; the compiled signature coerces it back to int at run time."""
    out: dict[int, str] = {}
    for k, v in state.items():
        idx: int | None = None
        if isinstance(v, bool):
            idx = None
        elif isinstance(v, int):
            idx = v
        elif isinstance(v, str) and v.isdigit():
            idx = int(v)
        if idx is not None and 0 <= idx < 1000 and idx not in out:
            out[idx] = str(k)
    return out


def _search(node: Any, path: str, target: Any, depth: int,
            index_names: dict[int, str]) -> list[str]:
    out: list[str] = []
    if _equal(node, target):
        out.append(path)
    if depth <= 0:
        return out
    if isinstance(node, dict):
        for k, v in node.items():
            out.extend(_search(v, f"{path}.{k}", target, depth - 1, index_names))
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            out.extend(_search(v, f"{path}[{i}]", target, depth - 1, index_names))
            if i in index_names:
                out.extend(_search(v, f"{path}[${index_names[i]}]", target, depth - 1, index_names))
    return out


def _equal(a: Any, b: Any) -> bool:
    """Exact typed equality — but int/float that are numerically equal count, and
    bools never equal numbers (so True != 1 here)."""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


__all__ = ["find_source", "find_all_sources", "is_meaningful"]
