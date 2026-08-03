"""Credential storage and provider inference."""

from __future__ import annotations

import pytest

from jdsl import config


@pytest.mark.parametrize(
    "model_id,provider",
    [
        ("claude-opus-4-8", "anthropic"),
        ("deepseek-chat", "deepseek"),
        ("gpt-4o", "openai"),
        ("o3-mini", "openai"),
        ("gemini-2.0", "google"),
        ("something-unknown", "anthropic"),  # default
    ],
)
def test_provider_for_model(model_id, provider):
    assert config.provider_for_model(model_id) == provider


def test_add_keys_dedupes_and_merges(isolated_config):
    config.add_keys("deepseek", ["a", "b"])
    merged = config.add_keys("deepseek", ["b", "c"])
    assert merged == ["a", "b", "c"]
    assert config.load()["deepseek"]["api_keys"] == ["a", "b", "c"]


def test_add_keys_rejects_unknown_provider(isolated_config):
    with pytest.raises(ValueError, match="Unknown provider"):
        config.add_keys("nope", ["x"])


def test_keys_for_prefers_stored_over_env(isolated_config, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
    config.add_keys("deepseek", ["stored"])
    assert config.keys_for("deepseek") == ["stored"]


def test_keys_for_falls_back_to_env(isolated_config, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    assert config.keys_for("anthropic") == ["env-key"]


def test_keys_for_empty_when_nothing(isolated_config):
    assert config.keys_for("openai") == []


def test_auth_path_under_xdg(isolated_config):
    assert str(config.auth_path()).startswith(str(isolated_config))
    assert config.auth_path().name == "auth.json"
