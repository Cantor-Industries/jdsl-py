"""Provider dispatch and key rotation — backends are faked, never called."""

from __future__ import annotations

import pytest

from jdsl import config, provider
from jdsl.router import NoKeysError


def test_generate_dispatches_by_model_prefix(isolated_config, monkeypatch):
    config.add_keys("anthropic", ["k"])
    config.add_keys("deepseek", ["k"])
    monkeypatch.setattr(provider, "_anthropic_generate", lambda **kw: "ANTHROPIC")
    monkeypatch.setattr(provider, "_openai_compatible_generate", lambda **kw: f"OAI:{kw['provider']}")

    lm = provider.LanguageModel()
    assert lm.generate(system="", messages=[], model_id="claude-opus-4-8") == "ANTHROPIC"
    assert lm.generate(system="", messages=[], model_id="deepseek-chat") == "OAI:deepseek"


def test_generate_rotates_key_on_auth_error(isolated_config, monkeypatch):
    config.add_keys("deepseek", ["k1", "k2"])
    seen: list[str] = []
    n = {"i": 0}

    def flaky(**kw):
        seen.append(kw["api_key"])
        n["i"] += 1
        if n["i"] == 1:
            raise provider._RetryableAuthError
        return "ok"

    monkeypatch.setattr(provider, "_openai_compatible_generate", flaky)
    lm = provider.LanguageModel()
    assert lm.generate(system="", messages=[], model_id="deepseek-chat") == "ok"
    assert seen == ["k1", "k2"]  # rotated to the second key after the failure


def test_generate_raises_after_max_attempts(isolated_config, monkeypatch):
    config.add_keys("deepseek", ["k"])

    def always(**kw):
        raise provider._RetryableAuthError

    monkeypatch.setattr(provider, "_openai_compatible_generate", always)
    with pytest.raises(RuntimeError, match="failed after"):
        provider.LanguageModel().generate(system="", messages=[], model_id="deepseek-chat")


def test_generate_without_keys_raises(isolated_config):
    with pytest.raises(NoKeysError):
        provider.LanguageModel().generate(system="", messages=[], model_id="deepseek-chat")
