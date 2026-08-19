"""Multi-turn sessions: a stateful conversation over a persistent RunContext.

`Root.run(**inputs)` is single-shot — it builds a fresh RunContext, ticks once,
and returns. That's the right shape for a skill that maps inputs to outputs, but
it can't hold a *conversation*: a benchmark like tau-bench alternates an agent
turn with a simulated-user turn many times, and the agent must remember every
earlier turn and keep mutating a shared tool environment across all of them.

A `Session` carries one RunContext (blackboard + window + model) across many
`send()` calls. It runs in one of two modes, which happen to be exactly the two
arms you want to compare on a reliability benchmark:

* **flat** (model-steered) — pass `tools=[...]`. Each `send()` runs a native
  function-calling loop (the same primitive `react` uses) until the model emits
  a text turn with no tool calls; that text is its reply to the user. This is
  the baseline every framework submits: policy lives in the system prompt.

* **tree** (tree-steered) — pass `tree=<node>`. Each `send()` seeds the incoming
  user message onto the persistent blackboard, ticks the tree, and returns the
  reply the tree wrote back. Policy lives in `seq`/`sel`/`check` guards the model
  can't step around, and state (auth flags, cart contents, …) persists on the
  blackboard between turns. This is the arm whose reliability advantage the
  determinism thesis predicts.

Both modes talk to tools through the exact same provider primitives as the rest
of jdsl, so a Session is offline-testable with the FakeModel used everywhere
else in the suite.
"""

from __future__ import annotations

from typing import Any

from jdsl.context import Blackboard, RunContext
from jdsl.tree import (
    FAILED_CALLS_KEY,
    Node,
    _failed_calls_note,
    _known_failure,
    _looks_like_error,
    _record_failure,
    _tool_schema,
)


class Session:
    """A persistent multi-turn conversation over a jdsl agent.

    Construct with EITHER `tools=` (flat, model-steered) OR `tree=` (tree-steered),
    plus a `model` and `model_id`. Drive it with `send(user_message) -> reply`.
    The blackboard, and in flat mode the message history, live for the lifetime
    of the Session — that is what makes it multi-turn.
    """

    def __init__(
        self,
        *,
        model: Any,
        model_id: str | None = None,
        system: str = "",
        tools: list[Any] | None = None,
        tree: Node | None = None,
        max_tool_steps: int = 20,
        input_key: str = "user_message",
        reply_key: str = "reply",
        transcript_key: str = "transcript",
        inputs: dict[str, Any] | None = None,
    ) -> None:
        if (tools is None) == (tree is None):
            raise ValueError("Session needs exactly one of `tools=` (flat mode) or `tree=` (tree mode).")
        self.model = model
        self.model_id = model_id
        self.system = system
        self.max_tool_steps = max_tool_steps
        self.input_key = input_key
        self.reply_key = reply_key
        self.transcript_key = transcript_key

        # One RunContext for the whole conversation: the blackboard and window
        # persist across every send(), which is the entire point of a Session.
        self.ctx = RunContext(blackboard=Blackboard(inputs or {}), model=model, model_id=model_id)
        if system:
            self.ctx.window.push_system(system)

        self.tree = tree
        self._tools = {t.name: t for t in (tools or [])}
        self._specs = [
            {"name": t.name, "description": t.description,
             "parameters": getattr(t, "parameters", None) or _tool_schema(t.fn)}
            for t in (tools or [])
        ]
        # Flat mode keeps a persistent neutral history (user/assistant/tool items).
        self.history: list[dict[str, Any]] = []
        # Per-turn trace of tool calls, handy for graders/debugging.
        self.last_tool_calls: list[dict[str, Any]] = []

    @property
    def blackboard(self) -> Blackboard:
        return self.ctx.blackboard

    def send(self, user_message: str) -> str:
        """Advance the conversation by one user turn; return the agent's reply."""
        self.last_tool_calls = []
        return self._send_tree(user_message) if self.tree is not None else self._send_flat(user_message)

    # -- flat / model-steered ------------------------------------------------

    def _send_flat(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})
        for _ in range(self.max_tool_steps):
            # Surface already-failed calls so the model stops re-issuing them
            # (the blackboard persists across turns, so this spans the whole episode).
            note = _failed_calls_note(self.ctx.blackboard.get(FAILED_CALLS_KEY) or [])
            system = self.ctx.window.system + (f"\n\n{note}" if note else "")
            turn = self.model.converse(
                system=system,
                messages=self.history,
                tools=self._specs,
                model_id=self.model_id,
            )
            if not turn.tool_calls:
                reply = turn.text.strip()
                self.history.append({"role": "assistant", "content": reply})
                return reply
            self.history.append(
                {"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls}
            )
            for call in turn.tool_calls:
                result = self._invoke(call.name, call.arguments)
                self.history.append(
                    {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": str(result)}
                )
        # Exhausted tool steps without turning back to the user. Surface it
        # rather than looping forever; a grader will read this as a failed turn.
        fallback = "(agent exceeded max tool steps without replying)"
        self.history.append({"role": "assistant", "content": fallback})
        return fallback

    def _invoke(self, name: str, arguments: dict[str, Any]) -> Any:
        self.last_tool_calls.append({"name": name, "arguments": arguments})
        failed = list(self.ctx.blackboard.get(FAILED_CALLS_KEY) or [])
        known = _known_failure(failed, name, arguments)
        if known is not None:  # exact repeat of a known-bad call: don't fire it again
            return (f"error: this exact call already failed ({known['error']}). "
                    "Do not repeat it — change the arguments or ask the user.")
        tool = self._tools.get(name)
        if tool is None:
            result: Any = f"error: no tool named {name!r}"
        else:
            try:
                result = tool(**arguments)
            except Exception as err:  # tool errors are observations, not crashes
                result = f"error: {type(err).__name__}: {err}"
        if _looks_like_error(result):
            self.ctx.blackboard.set(FAILED_CALLS_KEY,
                                    _record_failure(failed, name, arguments, result), writer="session")
        return result

    # -- tree / tree-steered -------------------------------------------------

    def _send_tree(self, user_message: str) -> str:
        assert self.tree is not None
        self._append_transcript("User", user_message)
        self.ctx.blackboard.set(self.input_key, user_message, writer="user")
        # Fresh per-turn scratch so oneshot/latching decorators treat one user
        # turn as one "run"; the blackboard itself persists across turns.
        self.ctx.state.clear()
        self.tree.tick(self.ctx)
        reply = self.ctx.blackboard.get(self.reply_key)
        reply = "" if reply is None else str(reply)
        self._append_transcript("Agent", reply)
        return reply

    def _append_transcript(self, speaker: str, text: str) -> None:
        """Maintain a running plain-text conversation on the blackboard. A leaf
        (predict/react) can take `transcript` as an input field to see the whole
        dialogue — the memory a single re-ticked tree would otherwise lack, since
        each tick rebuilds its own history from scratch. The transcript reflects
        turns *before* the current tree tick, plus the user line that triggered
        it (appended before tick); the agent's reply is appended after."""
        prior = self.ctx.blackboard.get(self.transcript_key) or ""
        line = f"{speaker}: {text}"
        self.ctx.blackboard.set(self.transcript_key, f"{prior}\n{line}".strip(), writer="session")


__all__ = ["Session"]
