"""Use a local open-weights Hugging Face model as a jdsl LLM provider.

jdsl's model is duck-typed: `root(...).run(model=obj)` and `Session(model=obj)`
accept any object exposing

    generate(*, system, messages, model_id=None) -> str          # predict leaves
    converse(*, system, messages, tools, model_id=None) -> ModelTurn  # react leaves

so nothing in jdsl needs to change to run on a local model — you just hand it an
`HFModel` instead of the API-backed `LanguageModel`.

Tool calling adapts to the model. When the model supports **native** tool calling
— Gemma 4, or any chat template that declares tool tokens (auto-detected, or
forced with `native_tools=`) — tools are rendered through the tokenizer's chat
template (`apply_chat_template(tools=...)`), so the model emits tool calls in the
exact format it was trained on and we parse its native `<|tool_call>` spans. For
everything else we fall back to a **prompt-based** protocol: describe the tools in
the system text and ask for a single JSON object `{"tool": ..., "arguments": {...}}`,
which parses uniformly across any instruct model without per-model glue.

Predict leaves (`generate`) fold system into the first user turn — some templates
reject a system role — while native `converse` sends a real system turn, which
tool-capable templates support (and where the tool declarations belong).

Requires `transformers` + `torch` (present in Colab). Import is lazy so this
module loads without them.
"""

from __future__ import annotations

import json
import re
from typing import Any

from jdsl import ModelTurn, ToolCall


class HFModel:
    """A jdsl-shaped provider backed by a local transformers CausalLM.

    Pass an already-loaded `model` + `tokenizer`, or a model id to load:

        HFModel.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
        HFModel(model=model, tokenizer=tokenizer)
    """

    def __init__(self, *, model: Any, tokenizer: Any, max_new_tokens: int = 512,
                 native_tools: bool | None = None) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.max_new_tokens = max_new_tokens
        self._call_id = 0
        # Native tool-calling (render tools through the chat template) when the
        # model supports it — Gemma 4, or any template that declares tool tokens —
        # else the prompt-based JSON protocol. Pass native_tools=True/False to force.
        self.native_tools = self._detect_native_tools() if native_tools is None else native_tools

    def _detect_native_tools(self) -> bool:
        cfg = getattr(self.model, "config", None)
        arch = " ".join(getattr(cfg, "architectures", None) or [])
        model_type = getattr(cfg, "model_type", "") or ""
        if "gemma4" in f"{arch} {model_type}".lower(): return True
        template = getattr(self.tokenizer, "chat_template", None) or ""
        return "tool_call" in template  # template advertises native tool-calling

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
        """react leaves: one tool-calling turn. Native (tools rendered through the
        chat template) for models that support it, prompt-based JSON otherwise."""
        return (self._converse_native(system, messages, tools) if self.native_tools
                else self._converse_prompted(system, messages, tools))

    def _turn_from_calls(self, calls: list[dict], fallback_text: str) -> ModelTurn:
        if not calls:
            return ModelTurn(text=fallback_text)
        out: list[ToolCall] = []
        for c in calls:
            self._call_id += 1
            out.append(ToolCall(id=str(self._call_id), name=c["tool"], arguments=c.get("arguments", {})))
        return ModelTurn(text="", tool_calls=out)

    # -- native tool calling (Gemma 4 & friends) -----------------------------

    def _converse_native(self, system: str, messages: list[dict], tools: list[dict]) -> ModelTurn:
        """Render tools via the tokenizer's chat template so the model emits tool
        calls in the format it was trained on (Gemma 4's tool tokens), not a
        hand-rolled JSON-in-prose protocol. System is a real system turn here — a
        tool-capable template supports one — and tool declarations ride in it."""
        chat = self._to_native_chat(system, messages)
        schemas = [self._as_function_schema(t) for t in tools]
        raw = self._complete_tools(chat, schemas)
        return self._turn_from_calls(self._parse_native_tool_calls(raw), self._clean_text(raw))

    def _complete_tools(self, chat: list[dict], tools: list[dict]) -> str:
        import torch  # lazy
        # Same render->tokenize->positional-input_ids path as _complete (keeps
        # multimodal generate() happy), but passes tools= so the template emits the
        # tool declarations, and keeps special tokens so tool-call markers survive.
        prompt = self.tokenizer.apply_chat_template(
            chat, tools=tools, add_generation_prompt=True, tokenize=False)
        enc = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(self.model.device)
        input_ids = enc["input_ids"]
        with torch.no_grad():
            out = self.model.generate(
                input_ids, attention_mask=enc.get("attention_mask"),
                max_new_tokens=self.max_new_tokens, do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
            )
        return self.tokenizer.decode(out[0][input_ids.shape[-1]:], skip_special_tokens=False).strip()

    @staticmethod
    def _to_native_chat(system: str, messages: list[dict]) -> list[dict]:
        """Neutral react history -> HF-standard chat messages the template renders:
        a real system turn, assistant turns carrying `tool_calls`, and `tool` result
        turns (rather than folding everything into user text)."""
        chat: list[dict] = [{"role": "system", "content": system}] if system else []
        for m in messages:
            role = m["role"]
            if role == "assistant" and m.get("tool_calls"):
                chat.append({"role": "assistant", "content": m.get("content") or "",
                             "tool_calls": [{"type": "function",
                                             "function": {"name": c.name, "arguments": c.arguments}}
                                            for c in m["tool_calls"]]})
            elif role == "tool":
                chat.append({"role": "tool", "name": m.get("name"), "content": str(m.get("content", ""))})
            else:
                chat.append({"role": role, "content": m.get("content", "")})
        return chat

    @staticmethod
    def _as_function_schema(tool: dict) -> dict:
        """A jdsl tool spec -> the OpenAI function-schema shape templates expect."""
        return {"type": "function", "function": {
            "name": tool["name"], "description": tool.get("description", ""),
            "parameters": tool.get("parameters") or {"type": "object", "properties": {}}}}

    def _parse_native_tool_calls(self, raw: str) -> list[dict]:
        """Extract tool calls from generated text. Prefer the model's native
        `<|tool_call>…<tool_call|>` spans; fall back to a bare JSON object carrying a
        name/arguments — tolerant, because the exact wrapper varies by model."""
        spans = re.findall(r"<\|tool_call\|?>(.*?)<\|?tool_call\|>", raw, re.DOTALL)
        calls = [c for span in spans if (c := self._parse_tool_call(span)) is not None]
        if calls:
            return calls
        one = self._parse_tool_call(raw)
        return [one] if one is not None else []

    def _clean_text(self, raw: str) -> str:
        """Strip special-token markers (`<|turn>`, `<turn|>`, `<|channel>`, …) so a
        plain-text answer reaches the user clean even when decoded with specials."""
        return re.sub(r"<\|?[a-zA-Z_]+\|?>", "", raw).strip()

    # -- prompt-based tool calling (other models) ----------------------------

    def _converse_prompted(self, system: str, messages: list[dict], tools: list[dict]) -> ModelTurn:
        sys_text = (system + "\n\n" + self._tool_instructions(tools)).strip()
        text = self._complete(self._to_chat(sys_text, self._flatten(messages)))
        return self._turn_from_calls(([self._parse_tool_call(text)] if self._parse_tool_call(text) else []),
                                     text)

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
            # accept both the prompt protocol's "tool" and the native format's "name"
            name = obj.get("tool") or obj.get("name") if isinstance(obj, dict) else None
            if name:
                return {"tool": name, "arguments": obj.get("arguments", {})}
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
