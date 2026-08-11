"""Decorators, deterministically (no LLM, no key) — so you can see them plainly.

- `optional(...)` wraps a best-effort audit step: it returns FAILURE, but optional
  converts that to SUCCESS so it can't abort the sequence.
- `invert(check(...))` is a negated guard: "allow unless banned".

Try it:
  uv run jdsl show examples/gate.py                    # render the tree
  uv run jdsl run examples/gate.py -i role=admin       # -> granted
  uv run jdsl run examples/gate.py -i role=guest       # -> allowed (not banned)
  uv run jdsl run examples/gate.py -i role=banned      # -> blocked (nothing runs)
"""

from jdsl import Status, act, check, invert, optional, root, sel, seq, tool


@tool
def audit() -> Status:
    """Pretend the audit sink is down — reports FAILURE."""
    return Status.FAILURE


@tool
def grant() -> None: print("→ access GRANTED (admin)")


@tool
def allow() -> None: print("→ access ALLOWED")


skill = (
    root("Gate", system="access control")
    .do(
        seq(
            optional(act(audit)),                       # best-effort; failure must not block
            sel(
                seq(check("role", "admin"), act(grant)),
                seq(invert(check("role", "banned")), act(allow)),  # allow unless banned
            ),
        )
    )
)


if __name__ == "__main__":
    for role in ("admin", "guest", "banned"):
        print(f"role={role!r}:", end=" ")
        skill.run(role=role)                # the grant/allow tools print their own outcome
        if role == "banned": print("→ BLOCKED")
