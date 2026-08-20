"""The restricted guard-expression language (design §21.2).

Compiled packages must not ship arbitrary Python (§22.3). Guards are instead a
small, safe, JSON expression tree evaluated against the blackboard. Operators are
a fixed set; operands are literals, refs, or simple JSON paths. Anything a package
can express here is reviewable and sandbox-safe by construction.

Expression grammar (all nodes are JSON objects with a single operator key)::

    {"exists": <operand>}
    {"eq": [<operand>, <operand>]}      # also neq, lt, lte, gt, gte
    {"in": [<operand>, <operand>]}      # membership: left in right
    {"and": [<expr>, ...]}              # also or
    {"not": <expr>}

An <operand> is either:
    {"ref": "customer.id"}              # resolved from the blackboard by path
    {"const": <json literal>}           # a literal value
    <bare json literal>                 # shorthand for {"const": ...}

Paths support dotted keys and bracket indexing, and a `$name` index is itself a
blackboard lookup (so `orders[$selected_index].id` works, §21.1)::

    order.status
    orders[0].id
    orders[$selected_index].id
"""

from __future__ import annotations

import re
from typing import Any

_MISSING = object()


class ExprError(ValueError):
    """A malformed guard expression (raised at validate/lower time, not runtime)."""


_PATH_TOKEN = re.compile(r"[^.\[\]]+|\[[^\]]*\]")

# operators that compare two ordered operands
_BINARY = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
}

VALID_OPERATORS = frozenset({"exists", "in", "and", "or", "not", *_BINARY})


def resolve_path(path: str, blackboard: dict[str, Any]) -> Any:
    """Resolve a dotted/bracketed path against the blackboard. Returns `_MISSING`
    (a sentinel) if any step is absent, so `exists` can distinguish absent from a
    stored `None`."""
    if path in blackboard:
        return blackboard[path]
    cur: Any = _MISSING
    first = True
    for tok in _PATH_TOKEN.findall(path):
        if tok.startswith("["):
            index_expr = tok[1:-1].strip()
            index = _resolve_index(index_expr, blackboard)
            cur = _index_into(cur, index)
        elif first:
            cur = blackboard.get(tok, _MISSING)
        else:
            cur = _index_into(cur, tok)
        first = False
        if cur is _MISSING:
            return _MISSING
    return cur


def _resolve_index(expr: str, blackboard: dict[str, Any]) -> Any:
    if expr.startswith("$"):
        return blackboard.get(expr[1:], _MISSING)
    if expr.lstrip("-").isdigit():
        return int(expr)
    return expr.strip("'\"")


def _index_into(cur: Any, key: Any) -> Any:
    if cur is _MISSING or key is _MISSING:
        return _MISSING
    try:
        if isinstance(cur, dict):
            return cur.get(key, _MISSING)
        if isinstance(cur, (list, tuple)) and isinstance(key, int):
            return cur[key] if -len(cur) <= key < len(cur) else _MISSING
    except (TypeError, KeyError, IndexError):
        return _MISSING
    return _MISSING


def _operand(spec: Any, blackboard: dict[str, Any]) -> Any:
    if isinstance(spec, dict) and set(spec) == {"ref"}:
        val = resolve_path(spec["ref"], blackboard)
        return None if val is _MISSING else val
    if isinstance(spec, dict) and set(spec) == {"const"}:
        return spec["const"]
    return spec  # bare literal


def evaluate(expr: Any, blackboard: dict[str, Any]) -> bool:
    """Evaluate a guard expression to a bool against the blackboard."""
    if not isinstance(expr, dict) or len(expr) != 1:
        raise ExprError(f"expression must be a single-operator object, got {expr!r}")
    op, arg = next(iter(expr.items()))
    if op == "exists":
        return resolve_path(_ref_of(arg), blackboard) is not _MISSING
    if op == "not":
        return not evaluate(arg, blackboard)
    if op in ("and", "or"):
        if not isinstance(arg, list):
            raise ExprError(f"{op!r} needs a list of expressions")
        results = (evaluate(e, blackboard) for e in arg)
        return all(results) if op == "and" else any(results)
    if op == "in":
        left, right = _pair(op, arg)
        container = _operand(right, blackboard)
        try:
            return _operand(left, blackboard) in container
        except TypeError:
            return False
    if op in _BINARY:
        left, right = _pair(op, arg)
        a, b = _operand(left, blackboard), _operand(right, blackboard)
        try:
            return bool(_BINARY[op](a, b))
        except TypeError:
            return False
    raise ExprError(f"unknown operator {op!r}; allowed: {sorted(VALID_OPERATORS)}")


def _pair(op: str, arg: Any) -> tuple[Any, Any]:
    if not isinstance(arg, list) or len(arg) != 2:
        raise ExprError(f"{op!r} needs exactly two operands, got {arg!r}")
    return arg[0], arg[1]


def _ref_of(arg: Any) -> str:
    if isinstance(arg, dict) and "ref" in arg:
        return arg["ref"]
    if isinstance(arg, str):
        return arg
    raise ExprError(f"exists needs a ref/path, got {arg!r}")


def validate_expr(expr: Any) -> list[str]:
    """Static-check an expression tree without a blackboard (§32.1). Returns a list
    of problems; empty means well-formed."""
    problems: list[str] = []
    _validate(expr, problems)
    return problems


def _validate(expr: Any, problems: list[str]) -> None:
    if not isinstance(expr, dict) or len(expr) != 1:
        problems.append(f"not a single-operator object: {expr!r}")
        return
    op, arg = next(iter(expr.items()))
    if op not in VALID_OPERATORS:
        problems.append(f"unknown operator {op!r}")
        return
    if op == "exists":
        try:
            _ref_of(arg)
        except ExprError as e:
            problems.append(str(e))
    elif op == "not":
        _validate(arg, problems)
    elif op in ("and", "or"):
        if not isinstance(arg, list):
            problems.append(f"{op!r} needs a list")
        else:
            for e in arg:
                _validate(e, problems)
    elif op == "in" or op in _BINARY:
        if not isinstance(arg, list) or len(arg) != 2:
            problems.append(f"{op!r} needs two operands")


__all__ = ["evaluate", "resolve_path", "validate_expr", "ExprError", "VALID_OPERATORS"]
