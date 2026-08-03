"""The LLM backend. LanguageModel.generate dispatches by model-id prefix
(claude*→Anthropic, deepseek*/gpt*/o*→OpenAI-compatible), pulls the key from a
per-provider RoundRobinRouter, and rotates it on auth/rate-limit failures."""

from __future__ import annotations

from jdsl import config
from jdsl.router import RoundRobinRouter

DEFAULT_MODEL = "claude-opus-4-8"
_MAX_ATTEMPTS = 5


class _RetryableAuthError(Exception):
    """Marker: an auth/balance/rate-limit failure worth rotating keys for."""


class LanguageModel:
    """Provider-dispatching language model with key rotation."""

    def __init__(self) -> None:
        self._routers: dict[str, RoundRobinRouter] = {}

    @classmethod
    def from_config(cls) -> LanguageModel: return cls()

    def _router(self, provider: str) -> RoundRobinRouter:
        if provider not in self._routers: self._routers[provider] = RoundRobinRouter(provider)
        return self._routers[provider]

    def generate(self, *, system: str, messages: list[dict[str, str]], model_id: str | None = None) -> str:
        model = model_id or DEFAULT_MODEL
        provider = config.provider_for_model(model)
        router = self._router(provider)
        backend = _anthropic_generate if provider == "anthropic" else _openai_compatible_generate
        last_error: Exception | None = None
        for _ in range(_MAX_ATTEMPTS):
            try:
                return backend(api_key=router.current(), provider=provider, model=model,
                               system=system, messages=messages)
            except _RetryableAuthError as err:
                last_error = err.__cause__ or err
                router.rotate()
        raise RuntimeError(f"LanguageModel.generate failed after {_MAX_ATTEMPTS} attempts "
                           f"for provider {provider!r}.") from last_error


def _anthropic_generate(*, api_key, provider, model, system, messages) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(model=model, max_tokens=16000,
                                           system=system or anthropic.NOT_GIVEN,
                                           messages=messages)  # type: ignore[arg-type]
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.RateLimitError) as err:
        raise _RetryableAuthError from err
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")


def _openai_compatible_generate(*, api_key, provider, model, system, messages) -> str:
    import openai
    client = openai.OpenAI(api_key=api_key, base_url=config.BASE_URLS.get(provider))
    chat = ([{"role": "system", "content": system}] if system else []) + list(messages)
    try:
        # temperature=0 so predict leaves decode deterministically
        response = client.chat.completions.create(model=model, max_tokens=16000, temperature=0,
                                                  messages=chat)  # type: ignore[arg-type]
    except (openai.AuthenticationError, openai.PermissionDeniedError, openai.RateLimitError) as err:
        raise _RetryableAuthError from err
    return response.choices[0].message.content or ""


__all__ = ["LanguageModel", "DEFAULT_MODEL"]
