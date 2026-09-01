# Providers, Models, and Keys

## Provider Inference

You never name a provider in a skill, only a model id. The provider is derived
from the id:

| Model id prefix | Provider | Backend |
| --------------- | -------- | ------- |
| `claude-*` | `anthropic` | Anthropic SDK |
| `deepseek-*` | `deepseek` | OpenAI SDK with `https://api.deepseek.com` |
| `gpt-*`, `o1/o3/o4-*` | `openai` | OpenAI SDK |
| `gemini-*` | `google` | provider slot exists; backend is not wired yet |

```python
root("S").model("deepseek-chat")   # DeepSeek
root("S").model("claude-opus-4-8") # Anthropic
```

DeepSeek is OpenAI-compatible, so it runs through the OpenAI SDK with a DeepSeek
base URL. OpenAI-compatible calls use `temperature=0` for stable structured
output.

## Keys

Keys are resolved per provider, in order:

1. Stored config at `~/.local/share/recon/auth.json`
   (`{"<provider>": {"api_keys": [...]}}`).
2. The provider's environment variable: `ANTHROPIC_API_KEY`,
   `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, or `GOOGLE_API_KEY`.

A `.env` in the working directory is loaded automatically via `python-dotenv`,
so adding `DEEPSEEK_API_KEY=...` to `.env` is enough. `.env` is gitignored; do
not commit keys.

Store keys explicitly with the CLI:

```bash
jdsl config add -p deepseek sk-...
jdsl config list
```

`config list` masks key values.

## Routing and Rotation

Each provider gets a `RoundRobinRouter` over its key list. On auth, permission,
or rate-limit errors, the router rotates to the next key and retries up to five
attempts.

Persistent per-key status tracking is not implemented yet.

## Model Injection in Tests

Skills accept an explicit model object:

```python
ctx = skill.run(model=fake_model("billing"), message="double charged")
```

The object only needs the `LanguageModel` shape used by the leaf: `generate` for
`predict`, and `converse` for `react`. The repository tests use this path to stay
offline.

## Adding a Provider

1. Add it to `SUPPORTED_PROVIDERS`, `ENV_KEYS`, and, if OpenAI-compatible,
   `BASE_URLS` in `jdsl/config.py`.
2. Teach `provider_for_model` the model-id prefix.
3. If it is not OpenAI-compatible, add a backend function in `jdsl/provider.py`
   and dispatch to it in `LanguageModel.generate` or `LanguageModel.converse`.
