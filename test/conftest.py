"""Shared fixtures. The suite is fast and offline — the LLM is never called."""

from __future__ import annotations

import pytest

from jdsl import config


class FakeModel:
    """A ``LanguageModel``-shaped stub. Scripts replies and records calls.

    Pass one or more reply strings; they're returned in order (the last repeats).
    Inspect ``.calls`` to assert on the system prompt, messages, and model id
    that a ``predict`` leaf sent.
    """

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies) or ["{}"]
        self.calls: list[dict] = []
        self._i = 0

    def generate(self, *, system, messages, model_id=None) -> str:
        self.calls.append({"system": system, "messages": messages, "model_id": model_id})
        reply = self.replies[min(self._i, len(self.replies) - 1)]
        self._i += 1
        return reply


@pytest.fixture
def fake_model():
    """Factory: ``fake_model('{"category": "billing"}')`` -> a FakeModel."""
    return FakeModel


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point config at a temp dir and clear provider env vars, so tests never
    read the real ~/.local/share/recon/auth.json or a real key."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    for env in config.ENV_KEYS.values():
        monkeypatch.delenv(env, raising=False)
    return tmp_path
