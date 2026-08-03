"""Credential storage + provider inference. Keys live in
~/.local/share/recon/auth.json as {"<provider>": {"api_keys": [...]}}, and a
.env in the working directory is loaded on import."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # so DEEPSEEK_API_KEY etc. are picked up without exporting

SUPPORTED_PROVIDERS = ("anthropic", "openai", "deepseek", "google")

ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "google": "GOOGLE_API_KEY",
}

# OpenAI-compatible base URLs (Anthropic uses its own SDK, so it's absent).
BASE_URLS = {"deepseek": "https://api.deepseek.com", "openai": None}


def provider_for_model(model_id: str) -> str:
    name = model_id.lower()
    if name.startswith("claude"): return "anthropic"
    if name.startswith("deepseek"): return "deepseek"
    if name.startswith(("gpt", "o1", "o3", "o4")): return "openai"
    if name.startswith("gemini"): return "google"
    return "anthropic"


def config_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "recon"


def auth_path() -> Path: return config_dir() / "auth.json"


def load() -> dict[str, dict[str, list[str]]]:
    path = auth_path()
    return json.loads(path.read_text()) if path.exists() else {}


def save(config: dict[str, dict[str, list[str]]]) -> None:
    path = auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))


def add_keys(provider: str, keys: list[str]) -> list[str]:
    """Merge keys into provider's list, de-duplicating. Returns the merged list."""
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}. Supported: {', '.join(SUPPORTED_PROVIDERS)}.")
    config = load()
    merged = list(config.get(provider, {}).get("api_keys", []))
    for key in keys:
        if key not in merged: merged.append(key)
    config[provider] = {"api_keys": merged}
    save(config)
    return merged


def keys_for(provider: str) -> list[str]:
    """Stored keys for provider, else the provider's env var."""
    stored = load().get(provider, {}).get("api_keys", [])
    if stored: return list(stored)
    env_value = os.environ.get(ENV_KEYS.get(provider, ""))
    return [env_value] if env_value else []
