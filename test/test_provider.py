"""Provider dispatch and key rotation — backends are faked, never called."""

from __future__ import annotations

import pytest

from jdsl import ToolCall, config, provider
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


# --- neutral <-> provider conversion (the native function-calling wire format) ---

def _history():
    """A full round: user, assistant-with-call, tool-result."""
    return [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "let me look",
         "tool_calls": [ToolCall(id="c1", name="lookup", arguments={"city": "Paris"})]},
        {"role": "tool", "tool_call_id": "c1", "name": "lookup", "content": "2.1M"},
    ]


def test_to_openai_shapes_tool_calls_and_results():
    out = provider._to_openai(_history())
    assert out[0] == {"role": "user", "content": "hi"}
    assert out[1]["role"] == "assistant"
    call = out[1]["tool_calls"][0]
    assert call["id"] == "c1" and call["function"]["name"] == "lookup"
    assert call["function"]["arguments"] == '{"city": "Paris"}'  # JSON-encoded string
    assert out[2] == {"role": "tool", "tool_call_id": "c1", "content": "2.1M"}


def test_to_anthropic_shapes_tool_use_and_result():
    out = provider._to_anthropic(_history())
    assert out[0] == {"role": "user", "content": "hi"}
    blocks = out[1]["content"]
    assert blocks[0] == {"type": "text", "text": "let me look"}
    assert blocks[1] == {"type": "tool_use", "id": "c1", "name": "lookup", "input": {"city": "Paris"}}
    # tool result is a *user*-role tool_result block (Anthropic's shape)
    assert out[2]["role"] == "user"
    assert out[2]["content"][0] == {"type": "tool_result", "tool_use_id": "c1", "content": "2.1M"}


def test_to_anthropic_coalesces_consecutive_tool_results():
    history = [
        {"role": "assistant", "content": "",
         "tool_calls": [ToolCall(id="a", name="t", arguments={}), ToolCall(id="b", name="t", arguments={})]},
        {"role": "tool", "tool_call_id": "a", "name": "t", "content": "r1"},
        {"role": "tool", "tool_call_id": "b", "name": "t", "content": "r2"},
    ]
    out = provider._to_anthropic(history)
    # both results land in one user turn (Anthropic rejects split tool_result turns)
    assert len(out) == 2
    assert [b["tool_use_id"] for b in out[1]["content"]] == ["a", "b"]
