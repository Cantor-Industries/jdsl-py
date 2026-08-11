"""The LLM backend. LanguageModel.generate dispatches by model-id prefix
(claude*→Anthropic, deepseek*/gpt*/o*→OpenAI-compatible), pulls the key from a
per-provider RoundRobinRouter, and rotates it on auth/rate-limit failures."""

from __future__ import annotations

import json

from jdsl import config
from jdsl.context import ModelTurn, ToolCall
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

    def converse(self, *, system: str, messages: list[dict], tools: list[dict],
                 model_id: str | None = None) -> ModelTurn:
        """One tool-calling turn. `messages` is neutral history (user/assistant/tool
        items), `tools` is neutral specs (name/description/parameters). Returns a
        ModelTurn: final text, or tool calls to run and feed back. Used by react."""
        model = model_id or DEFAULT_MODEL
        provider = config.provider_for_model(model)
        router = self._router(provider)
        backend = _anthropic_converse if provider == "anthropic" else _openai_converse
        last_error: Exception | None = None
        for _ in range(_MAX_ATTEMPTS):
            try:
                return backend(api_key=router.current(), provider=provider, model=model,
                               system=system, messages=messages, tools=tools)
            except _RetryableAuthError as err:
                last_error = err.__cause__ or err
                router.rotate()
        raise RuntimeError(f"LanguageModel.converse failed after {_MAX_ATTEMPTS} attempts "
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


def _anthropic_converse(*, api_key, provider, model, system, messages, tools) -> ModelTurn:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    specs = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
    try:
        response = client.messages.create(model=model, max_tokens=16000, temperature=0,
                                           system=system or anthropic.NOT_GIVEN,
                                           tools=specs,  # type: ignore[arg-type]
                                           messages=_to_anthropic(messages))  # type: ignore[arg-type]
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.RateLimitError) as err:
        raise _RetryableAuthError from err
    text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
    calls = [ToolCall(id=b.id, name=b.name, arguments=dict(b.input))  # type: ignore[arg-type]
             for b in response.content if getattr(b, "type", None) == "tool_use"]
    return ModelTurn(text=text, tool_calls=calls)


def _openai_converse(*, api_key, provider, model, system, messages, tools) -> ModelTurn:
    import openai
    client = openai.OpenAI(api_key=api_key, base_url=config.BASE_URLS.get(provider))
    specs = [{"type": "function", "function": t} for t in tools]
    chat = ([{"role": "system", "content": system}] if system else []) + _to_openai(messages)
    try:
        response = client.chat.completions.create(model=model, max_tokens=16000, temperature=0,
                                                  tools=specs,  # type: ignore[arg-type]
                                                  messages=chat)  # type: ignore[arg-type]
    except (openai.AuthenticationError, openai.PermissionDeniedError, openai.RateLimitError) as err:
        raise _RetryableAuthError from err
    msg = response.choices[0].message
    calls = [ToolCall(id=c.id, name=c.function.name, arguments=json.loads(c.function.arguments or "{}"))
             for c in (msg.tool_calls or [])]
    return ModelTurn(text=msg.content or "", tool_calls=calls)


def _to_anthropic(messages: list[dict]) -> list[dict]:
    """Neutral history -> Anthropic messages. Tool results are user-role
    tool_result blocks; consecutive ones coalesce into a single user turn."""
    out: list[dict] = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            content: list[dict] = []
            if m.get("content"): content.append({"type": "text", "text": m["content"]})
            content += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                        for c in m.get("tool_calls", [])]
            out.append({"role": "assistant", "content": content})
        else:  # tool result
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
    return out


def _to_openai(messages: list[dict]) -> list[dict]:
    """Neutral history -> OpenAI chat messages (tool_calls on assistant, tool role)."""
    out: list[dict] = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            entry: dict = {"role": "assistant", "content": m.get("content") or ""}
            if m.get("tool_calls"):
                entry["tool_calls"] = [{"id": c.id, "type": "function",
                                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                                       for c in m["tool_calls"]]
            out.append(entry)
        else:  # tool result
            out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
    return out


__all__ = ["LanguageModel", "DEFAULT_MODEL"]
