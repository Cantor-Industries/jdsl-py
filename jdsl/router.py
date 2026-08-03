"""Key rotation. RoundRobinRouter hands out a provider's keys and advances on
failure. SmartRouter is a placeholder alias (per-key status tracking is a gap)."""

from __future__ import annotations

from jdsl import config


class NoKeysError(RuntimeError): pass


class RoundRobinRouter:
    def __init__(self, provider: str = "anthropic") -> None:
        self.provider = provider
        self._keys = config.keys_for(provider)
        self._index = 0

    @property
    def has_keys(self) -> bool: return bool(self._keys)

    def current(self) -> str:
        if not self._keys:
            raise NoKeysError(f"No API key for {self.provider!r}. Add one with "
                              f"`jdsl config add -p {self.provider} <key>` or set the provider env var.")
        return self._keys[self._index % len(self._keys)]

    def rotate(self) -> None:
        if self._keys: self._index = (self._index + 1) % len(self._keys)


SmartRouter = RoundRobinRouter
