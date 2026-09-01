"""Content-addressed blob storage (design §10.3, §30).

Large content — database snapshots, big tool outputs, transcripts, source files —
should not sit inside the JSONL stream. Store it once under its sha256 digest and
reference the digest from events. Identical content dedupes to one blob.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class BlobStore:
    """Filesystem content-addressed store: `blobs/sha256/<digest>` (§10.3)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._dir = self.root / "sha256"
        self._dir.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes) -> str:
        """Store bytes, returning the `sha256:<digest>` ref. Idempotent."""
        digest = hashlib.sha256(data).hexdigest()
        path = self._dir / digest
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return f"sha256:{digest}"

    def put_json(self, value: Any) -> str:
        """Store a JSON-serializable value deterministically and return its ref."""
        blob = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return self.put(blob.encode("utf-8"))

    def put_text(self, text: str) -> str:
        return self.put(text.encode("utf-8"))

    def get(self, ref: str) -> bytes:
        return self._path(ref).read_bytes()

    def get_json(self, ref: str) -> Any:
        return json.loads(self.get(ref).decode("utf-8"))

    def has(self, ref: str) -> bool:
        return self._path(ref).exists()

    def _path(self, ref: str) -> Path:
        digest = ref.split(":", 1)[1] if ref.startswith("sha256:") else ref
        return self._dir / digest


__all__ = ["BlobStore"]
