# Providers, models & keys

## Provider is inferred from the model id

You never name a provider in a skill — only a model id. The provider is derived
from it:

| Model id prefix | Provider | Backend |
| --------------- | -------- | ------- |
| `claude-*` | `anthropic` | Anthropic SDK |
| `deepseek-*` | `deepseek` | OpenAI SDK → `https://api.deepseek.com` |
| `gpt-*`, `o1/o3/o4-*` | `openai` | OpenAI SDK |
| `gemini-*` | `google` | *not wired yet* |

```python
root("S").model("deepseek-chat")   # → DeepSeek
root("S").model("claude-opus-4-8") # → Anthropic
```

DeepSeek is OpenAI-compatible, so it runs through the OpenAI SDK with a different
base URL. `predict` leaves are decoded at `temperature=0` on the
OpenAI-compatible path for stable structured output (Anthropic's current models
reject the parameter, so it's omitted there).

## Keys

Keys are resolved per provider, in order:

1. Stored config at `~/.local/share/recon/auth.json`
   (`{"<provider>": {"api_keys": [...]}}`).
2. The provider's environment variable — `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`,
   `OPENAI_API_KEY`, `GOOGLE_API_KEY`.

A `.env` in the working directory is loaded automatically (via `python-dotenv`),
so dropping `DEEPSEEK_API_KEY=…` into `.env` is enough. **`.env` is gitignored —
never commit keys.**

Store keys explicitly with the CLI:

```bash
jdsl config add -p deepseek sk-...     # append (de-duplicated)
jdsl config list                       # print, masked
```

## Routing & rotation

Each provider gets a `RoundRobinRouter` over its key list. On an auth /
permission / rate-limit error the router rotates to the next key and the call is
retried (up to 5 attempts total). `SmartRouter` currently aliases
`RoundRobinRouter`; persistent per-key status tracking is a known gap.

## Adding a provider

1. Add it to `SUPPORTED_PROVIDERS`, `ENV_KEYS`, and (if OpenAI-compatible)
   `BASE_URLS` in `jdsl/config.py`.
2. Teach `provider_for_model` the model-id prefix.
3. If it isn't OpenAI-compatible, add a backend function in `jdsl/provider.py`
   and dispatch to it in `LanguageModel.generate`.
