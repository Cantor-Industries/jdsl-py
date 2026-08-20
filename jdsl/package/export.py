"""The in-memory behavior package and its export to disk (design §22, §35 PR13).

The canonical development representation is an unpacked directory (§22.1); the
transport form is a deterministic `.jdslpkg` ZIP (§22) whose bytes are a pure
function of its contents (fixed timestamps, sorted entries) so the same package
always hashes the same. No arbitrary code ships (§22.3): only restricted IR,
signatures, expressions, contracts, tests, and provenance.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jdsl.ir.schema import BehaviorIR
from jdsl.package.manifest import Manifest, NodeProvenance, ToolContract

_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)  # ZIP's minimum timestamp -> deterministic bytes


@dataclass
class BehaviorPackage:
    """A whole compiled behavior package held in memory (§22.1)."""
    manifest: Manifest
    ir: BehaviorIR
    tools: list[ToolContract] = field(default_factory=list)
    provenance: list[NodeProvenance] = field(default_factory=list)
    invariants: list[dict[str, Any]] = field(default_factory=list)
    postconditions: list[dict[str, Any]] = field(default_factory=list)
    tests: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # replay/guards/signatures
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    readme: str = ""

    def files(self) -> dict[str, str]:
        """The full set of package files as {relpath: text}, deterministically
        serialized. This is what both the directory and the ZIP write."""
        out: dict[str, str] = {}
        out["behavior.json"] = _dump(self.ir.to_dict())
        out["tools.json"] = _dump({"tools": [t.to_dict() for t in self.tools]})
        out["provenance.json"] = _dump({"nodes": [p.to_dict() for p in self.provenance]})
        for sid, sig in sorted(self.ir.signatures.items()):
            out[f"signatures/{sid}.json"] = _dump(sig.to_dict())
        out["contracts/invariants.json"] = _dump({"invariants": self.invariants})
        out["contracts/postconditions.json"] = _dump({"postconditions": self.postconditions})
        for name in ("replay", "guards", "signatures"):
            rows = self.tests.get(name, [])
            out[f"tests/{name}.jsonl"] = "".join(_dump(r, indent=None) + "\n" for r in rows)
        out["evidence/summary.json"] = _dump(self.evidence_summary)
        out["README.md"] = self.readme or _default_readme(self)
        # manifest last: it carries the digests of the other files (§22.2)
        self.manifest.files = {name: _sha256(text) for name, text in sorted(out.items())}
        out["manifest.json"] = _dump(self.manifest.to_dict())
        return out


def export_dir(pkg: BehaviorPackage, path: str | Path) -> Path:
    """Write the package as an unpacked directory (§22.1)."""
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in pkg.files().items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(text, encoding="utf-8")
    return root


def export_jdslpkg(pkg: BehaviorPackage, path: str | Path) -> Path:
    """Write the package as a deterministic `.jdslpkg` ZIP (§22)."""
    out = Path(path)
    if out.suffix != ".jdslpkg":
        out = out.with_suffix(".jdslpkg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_zip_bytes(pkg.files()))
    return out


def package_digest(pkg: BehaviorPackage) -> str:
    """A stable digest over the deterministic ZIP bytes (for signing later, §22.4)."""
    return "sha256:" + hashlib.sha256(_zip_bytes(pkg.files())).hexdigest()


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, files[name].encode("utf-8"))
    return buf.getvalue()


def _dump(value: Any, indent: int | None = 2) -> str:
    return json.dumps(value, sort_keys=True, indent=indent,
                      separators=(",", ": ") if indent else (",", ":"), default=str)


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _default_readme(pkg: BehaviorPackage) -> str:
    m = pkg.manifest
    reads = [t.logical_id for t in pkg.tools if t.effects.read_only]
    writes = [t.logical_id for t in pkg.tools if not t.effects.read_only]
    read_lines = [f"- {c}" for c in reads] or ["- (none)"]
    write_lines = [f"- {c}" for c in writes] or ["- (none)"]
    lines = [
        f"# {m.name}", "",
        f"Compiled jdsl behavior package (`{m.format}`), version {m.version}.", "",
        f"- Task family: {m.task_family or 'n/a'}",
        f"- Verification: {m.verification.get('status', 'unverified')}",
        f"- Source fidelity: {m.source.get('capture_fidelity', 'n/a')}, "
        f"episodes: {m.source.get('episode_count', 'n/a')}", "",
        "## Capabilities", "",
        "Reads:", *read_lines, "",
        "Writes:", *write_lines, "",
        "This package contains no arbitrary code — restricted IR, typed signatures,",
        "safe guard expressions, and references to trusted host tools only.",
    ]
    return "\n".join(lines) + "\n"


__all__ = ["BehaviorPackage", "export_dir", "export_jdslpkg", "package_digest"]
