"""Use a local open-weights Hugging Face model as a jdsl LLM provider.

jdsl's model is duck-typed: `root(...).run(model=obj)` and `Session(model=obj)`
accept any object exposing

    generate(*, system, messages, model_id=None) -> str          # predict leaves
    converse(*, system, messages, tools, model_id=None) -> ModelTurn  # react leaves

so nothing in jdsl needs to change to run on a local model — you just hand it an
`HFModel` instead of the API-backed `LanguageModel`.

Tool calling on arbitrary open models is done here **prompt-based**, not via each
model's native tool tokens: we describe the tools in the system text and ask for
a single JSON object `{"tool": ..., "arguments": {...}}` when the model wants to
call one, plain text when it wants to answer. That parses uniformly across any
instruct model (Qwen, Llama, Mistral, Gemma, …) without per-model glue. Models
with real tool support can still be wired via `apply_chat_template(tools=...)`;
this trades a little accuracy for working-everywhere.

System text is folded into the first user turn rather than sent as a system role,
because some chat templates (Gemma's, notably) reject a system role outright.

Requires `transformers` + `torch` (present in Colab). Import is lazy so this
module loads without them.
"""

from __future__ import annotations

import json
from typing import Any

from jdsl import ModelTurn, ToolCall


class HFModel:
    """A jdsl-shaped provider backed by a local transformers CausalLM.

    Pass an already-loaded `model` + `tokenizer`, or a model id to load:

        HFModel.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
        HFModel(model=model, tokenizer=tokenizer)
    """

    def __init__(self, *, model: Any, tokenizer: Any, max_new_tokens: int = 512) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.max_new_tokens = max_new_tokens
        self._call_id = 0

    @classmethod
    def from_pretrained(cls, model_id: str, *, max_new_tokens: int = 512, **kwargs: Any) -> HFModel:
        from transformers import AutoModelForCausalLM, AutoTokenizer  # lazy
        tok = AutoTokenizer.from_pretrained(model_id)
        kwargs.setdefault("device_map", "auto")
        model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
        return cls(model=model, tokenizer=tok, max_new_tokens=max_new_tokens)

    # -- jdsl provider interface ---------------------------------------------

    def generate(self, *, system: str, messages: list[dict], model_id: str | None = None) -> str:
        """predict leaves: one prompt in, free text out."""
        return self._complete(self._to_chat(system, self._plain(messages)))

    def converse(self, *, system: str, messages: list[dict], tools: list[dict],
                 model_id: str | None = None) -> ModelTurn:
        """react leaves: one tool-calling turn, prompt-based."""
        sys_text = (system + "\n\n" + self._tool_instructions(tools)).strip()
        text = self._complete(self._to_chat(sys_text, self._flatten(messages)))
        call = self._parse_tool_call(text)
        if call is not None:
            self._call_id += 1
            return ModelTurn(text="", tool_calls=[
                ToolCall(id=str(self._call_id), name=call["tool"], arguments=call.get("arguments", {}))
            ])
        return ModelTurn(text=text)

    # -- generation ----------------------------------------------------------

    def _complete(self, chat: list[dict]) -> str:
        import torch  # lazy
        # Render to a string first, then tokenize, then pass input_ids POSITIONALLY
        # to generate(). This is the compatible path across text and multimodal
        # models: handing generate() a BatchEncoding (via return_dict + **enc) makes
        # some multimodal generate() implementations treat the whole encoding as the
        # input tensor and blow up on `.shape`. The template already injects <bos>,
        # so add_special_tokens=False avoids a doubled BOS.
        prompt = self.tokenizer.apply_chat_template(chat, add_generation_prompt=True, tokenize=False)
        enc = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(self.model.device)
        input_ids = enc["input_ids"]
        with torch.no_grad():
            out = self.model.generate(
                input_ids, attention_mask=enc.get("attention_mask"),
                max_new_tokens=self.max_new_tokens, do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
            )
        return self.tokenizer.decode(out[0][input_ids.shape[-1]:], skip_special_tokens=True).strip()

    # -- message shaping -----------------------------------------------------

    @staticmethod
    def _plain(messages: list[dict]) -> list[dict]:
        """predict only sends simple user/assistant string messages."""
        return [{"role": m["role"], "content": m.get("content", "")} for m in messages]

    @staticmethod
    def _to_chat(system: str, messages: list[dict]) -> list[dict]:
        """Fold system text into the first user turn (system-role-free, so it
        works on templates that forbid a system role, e.g. Gemma)."""
        chat = [dict(m) for m in messages]
        if not system:
            return chat
        for m in chat:
            if m["role"] == "user":
                m["content"] = f"{system}\n\n{m['content']}"
                return chat
        return [{"role": "user", "content": system}, *chat]

    @staticmethod
    def _flatten(messages: list[dict]) -> list[dict]:
        """Neutral react history (assistant tool_calls, tool results) -> plain
        user/assistant turns a chat template can render."""
        out: list[dict] = []
        for m in messages:
            role = m["role"]
            if role == "user":
                out.append({"role": "user", "content": m["content"]})
            elif role == "assistant":
                parts = [m["content"]] if m.get("content") else []
                for c in m.get("tool_calls", []):
                    parts.append(json.dumps({"tool": c.name, "arguments": c.arguments}))
                out.append({"role": "assistant", "content": "\n".join(parts) or "(thinking)"})
            else:  # tool result -> report back as a user observation
                out.append({"role": "user", "content": f"[result of {m.get('name')}]: {m['content']}"})
        return out

    # -- prompt-based tool protocol ------------------------------------------

    @staticmethod
    def _tool_instructions(tools: list[dict]) -> str:
        lines = ["You can call tools. Available tools:"]
        for t in tools:
            props = list(t.get("parameters", {}).get("properties", {}))
            lines.append(f"- {t['name']}: {t.get('description', '')} (arguments: {props})")
        lines.append(
            'To call a tool, reply with ONLY a JSON object and nothing else: '
            '{"tool": "<tool_name>", "arguments": {<args>}}.'
        )
        lines.append("When you are ready to answer, reply in plain text with no JSON.")
        return "\n".join(lines)

    @staticmethod
    def _parse_tool_call(text: str) -> dict | None:
        for candidate in HFModel._json_objects(text):
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "tool" in obj:
                obj.setdefault("arguments", {})
                return obj
        return None

    @staticmethod
    def _json_objects(text: str) -> list[str]:
        """Candidate JSON-object substrings: the whole text first, then every
        brace-balanced ``{...}`` span. A depth counter (that ignores braces inside
        strings) means nested objects and surrounding prose both parse — unlike a
        non-greedy regex, which stops at the first inner ``}`` and mangles
        ``{"tool": ..., "arguments": {...}}``."""
        out = [text]
        depth = start = 0
        in_str = esc = False
        for i, c in enumerate(text):
            if in_str:
                if esc: esc = False
                elif c == "\\": esc = True
                elif c == '"': in_str = False
                continue
            if c == '"': in_str = True
            elif c == "{":
                if depth == 0: start = i
                depth += 1
            elif c == "}" and depth > 0:
                depth -= 1
                if depth == 0: out.append(text[start:i + 1])
        return out


__all__ = ["HFModel"]
