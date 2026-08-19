# Running the tau-bench benchmark in Colab (no API keys)

Everything in this directory was already wired to run tau-bench. The **only**
thing that ever blocked a run was not having a working API key. This doc runs the
exact same benchmark on a **free open-weights model in Colab** instead — nothing
about jdsl changes, we just hand it a local model.

## The one thing to understand first

tau-bench uses **two** LLMs every episode:

| Stream | What it is | In this repo |
| ------ | ---------- | ------------ |
| **Agent** | The thing being measured. A jdsl `Session` running your behavior tree. | `jdsl` + your model |
| **User-simulator** | tau-bench's *own* actor that plays the customer and talks to the agent. | tau-bench, via `litellm` |

The agent is jdsl — you plug in the model and you're done. The user-simulator is
**not** jdsl; it's tau-bench-internal. In the original plan it was a cheap API
model (`--user-model gpt-4o-mini`). With no API key, that second stream also has
to run on the local model, so we register the local model with `litellm` under a
provider name (`localhf`) and point tau-bench's user-sim at it.

That's the whole difference. Agent = plug in `llm`. User-sim = plug in the *same*
`llm` through litellm. Two plugs, one model.

## Where jdsl actually is

```
jdsl.bench.tau_bench_adapter.run_task_k
  └─ run_episode
       └─ Session(model=llm, tree=build_tree(...))     ← jdsl multi-turn agent
            every turn: tick the retail_policy.py tree  ← jdsl behavior tree
              sel / seq / check / react                 ← policy as tree guards
              react leaf → HFModel.converse             ← jdsl → local model
```

`model=llm` is the only injection point. The tree in `jdsl.bench.retail_policy`
is the research contribution; the local model is just what runs the leaves.

## Cell 1 — install

`bench` ships **inside** the jdsl package (`jdsl/bench/`), so `pip install` gives
you both — no clone needed. Import it as `jdsl.bench.…`.

```python
!pip install -q "git+https://github.com/Cantor-Industries/jdsl-py.git@t-bench"
!pip install -q "git+https://github.com/sierra-research/tau-bench.git"
```

That's it — `from jdsl.bench import tau_bench_adapter` and `from jdsl.hf import
HFModel` both resolve straight from the installed package.

## Cell 2 — load the open model as a jdsl provider

Use the **instruction-tuned** (`-it`) model. Gemma 4 ships its chat template as a
separate file that isn't auto-loaded, so we set it, and stop generation at the
end-of-turn token.

```python
import torch
from transformers import AutoProcessor, AutoModelForImageTextToText
from huggingface_hub import hf_hub_download

MODEL_ID = "google/gemma-4-E2B-it"

processor = AutoProcessor.from_pretrained(MODEL_ID)
model = AutoModelForImageTextToText.from_pretrained(
    MODEL_ID, device_map="auto", torch_dtype=torch.bfloat16)
tokenizer = processor.tokenizer

tokenizer.chat_template = open(hf_hub_download(MODEL_ID, "chat_template.jinja")).read()
eot = tokenizer.convert_tokens_to_ids("<turn|>")
model.generation_config.eos_token_id = [tokenizer.eos_token_id, eot]

from jdsl.hf import HFModel
llm = HFModel(model=model, tokenizer=tokenizer, max_new_tokens=256)   # the one plug
```

Quick sanity check that jdsl talks to the model at all:

```python
from jdsl import predict, RunContext
ctx = RunContext(model=llm, model_id="local")
ctx.blackboard["message"] = "I was double charged"
predict("message -> category").tick(ctx)
print(ctx.blackboard["category"])          # expect: billing
```

## Cell 3 — give tau-bench's user-simulator the same local model

This block is **not** jdsl — it feeds tau-bench's internal user actor so it too
runs without an API key.

```python
import litellm
from litellm import CustomLLM
from litellm.types.utils import ModelResponse, Choices, Message

class LocalHF(CustomLLM):
    def __init__(self, hf): self.hf = hf
    def completion(self, *args, **kwargs) -> ModelResponse:
        msgs   = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
        system = "\n".join(m["content"] for m in msgs if m.get("role") == "system")
        rest   = [m for m in msgs if m.get("role") != "system"]
        text   = self.hf.generate(system=system, messages=rest, model_id="local")
        r = ModelResponse()
        r.choices = [Choices(message=Message(role="assistant", content=text))]
        return r

litellm.custom_provider_map = [{"provider": "localhf", "custom_handler": LocalHF(llm)}]
```

## Cell 4 — run the benchmark

```python
from jdsl.bench import tau_bench_adapter as A
from jdsl.bench import retail_policy

tb = A._load_tau_bench()

def env_factory():
    return tb.get_env("retail", user_strategy="llm",
                      user_model="gemma", user_provider="localhf",   # -> LocalHF
                      task_split="test")

ARM   = "tree"        # "tree" = policy tree (the contribution); "flat" = prompt-only baseline
TASKS = [0, 1]        # start tiny — each task is many turns × two local streams
K     = 1             # trials per task for pass^k; raise once it works

episode_kwargs = dict(
    agent_model_id="local",
    model=llm,                                                   # agent = local model
    build_tree=(retail_policy.build_tree if ARM == "tree" else None),
    max_turns=10,
)

for t in TASKS:
    rewards = A.run_task_k(tb, env_factory, t, k=K, **episode_kwargs)
    ok = A.pass_hat_k(rewards)
    print(f"task {t}  arm={ARM}  rewards={rewards}  pass^{K}={'Y' if ok else 'N'}")
```

## Reading the result

- Rewards are `0.0` / `1.0` from tau-bench's database-state grader.
- A small open model will score low at first — that is expected. The experiment
  is the **gap between `ARM='flat'` and `ARM='tree'`** on the same tasks, not the
  absolute number: the thesis is that encoding policy in the tree (auth
  phase-gating, confirm-before-write) sheds fewer trials than putting it in the
  prompt.
- It is **slow**: two local model streams per turn. Keep `TASKS` and `K` small
  until you have a feel for the per-task wall time, then scale up.

## If something breaks

- `TypeError` from `env_factory()` → tau-bench's `get_env` kwargs have drifted
  between releases; the one place to adjust is `_load_tau_bench` / that call.
- User-sim produces garbage → the `LocalHF` shim is fine; it's the small model.
  Try a stronger open model in Cell 2 (any instruct model works — `HFModel` is
  model-agnostic).
