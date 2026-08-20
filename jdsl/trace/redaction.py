"""Redaction of sensitive values before durable persistence (design §31.2).

The harness may see secrets, customer data, and identifiers. Redaction happens
*before* events are written or shown to a compiler model (§31: "Redact before
durable persistence when possible"; "Do not upload secrets to a compiler model
merely because the trace contains them").

The default `Redactor` covers common secret patterns and configurable JSON paths.
It is deliberately conservative and deterministic — the same input always redacts
to the same placeholder, so redacted traces still support exact dataflow mining on
non-secret values.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# common secret-ish token shapes; conservative, matches whole values
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),            # OpenAI-style keys
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{16,}"),      # Anthropic keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),      # GitHub tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),                # AWS access key id
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),         # Google API key
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),   # Slack tokens
    re.compile(r"eyJ[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}"),  # JWT
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

_REDACTED = "«redacted»"


@dataclass
class Redactor:
    """Redacts secrets from arbitrary JSON-ish structures.

    - `patterns`: regexes whose matches inside strings are replaced.
    - `key_names`: object keys whose *values* are fully redacted (case-insensitive
      substring match), e.g. "password", "api_key", "token", "secret".
    - `json_paths`: dotted paths (e.g. "customer.email") to redact wherever they
      occur at any depth.
    """

    patterns: tuple[re.Pattern[str], ...] = _SECRET_PATTERNS
    key_names: tuple[str, ...] = ("password", "secret", "api_key", "apikey", "token", "authorization")
    json_paths: tuple[str, ...] = ()
    placeholder: str = _REDACTED
    enabled: bool = True

    def redact(self, value: Any, _path: str = "") -> Any:
        if not self.enabled:
            return value
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                child_path = f"{_path}.{k}" if _path else str(k)
                if self._key_is_secret(k) or self._path_is_secret(child_path):
                    out[k] = self.placeholder
                else:
                    out[k] = self.redact(v, child_path)
            return out
        if isinstance(value, (list, tuple)):
            return [self.redact(v, _path) for v in value]
        if isinstance(value, str):
            return self._redact_string(value)
        return value

    def _key_is_secret(self, key: Any) -> bool:
        k = str(key).lower()
        return any(name in k for name in self.key_names)

    def _path_is_secret(self, path: str) -> bool:
        return any(path == p or path.endswith("." + p) for p in self.json_paths)

    def _redact_string(self, s: str) -> str:
        for pat in self.patterns:
            s = pat.sub(self.placeholder, s)
        return s


def with_paths(paths: Iterable[str], **kwargs: Any) -> Redactor:
    """Convenience: a default redactor plus extra JSON paths to strip."""
    return Redactor(json_paths=tuple(paths), **kwargs)


__all__ = ["Redactor", "with_paths"]
