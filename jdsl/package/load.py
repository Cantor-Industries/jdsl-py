"""Load and bind a behavior package (design §40 runtime, §45 security model).

Loading treats a `.jdsl` package like software: verify the manifest format, verify file
digests, structurally validate the IR (§32.1), and reject anything malformed
*before* execution. Binding then attaches host-supplied tools and predicates
(§12.1); a missing required capability fails the bind, never a run.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jdsl.ir.lower import RuntimeBindings, lower
from jdsl.ir.schema import BehaviorIR, Signature
from jdsl.ir.validate import validate_ir
from jdsl.package.export import _sha256
from jdsl.package.manifest import PACKAGE_FORMAT, Manifest, NodeProvenance, ToolContract
from jdsl.tree import Node, Root

_SUPPORTED_FORMATS = {PACKAGE_FORMAT}


class PackageError(ValueError):
    """A package failed to load: bad format, digest mismatch, or invalid IR."""


@dataclass
class LoadedPackage:
    """A verified, in-memory package ready to bind and run."""
    manifest: Manifest
    ir: BehaviorIR
    tools: list[ToolContract]
    provenance: list[NodeProvenance]
    root_dir: Path | None = None

    @property
    def name(self) -> str:
        return self.manifest.name

    def capability(self, logical_id: str) -> ToolContract | None:
        return next((t for t in self.tools if t.logical_id == logical_id), None)

    def permissions(self) -> dict[str, list[str]]:
        """The reads/writes a host should display before binding (§45)."""
        reads = [t.logical_id for t in self.tools if t.effects.read_only]
        writes = [t.logical_id for t in self.tools if not t.effects.read_only]
        return {"reads": sorted(reads), "writes": sorted(writes)}

    def bind(self, tools: dict[str, Any], predicates: dict[str, Any] | None = None) -> Node:
        """Bind capabilities/predicates and lower to a runnable tree (§12.1)."""
        missing = [c for c in self.manifest.required_capabilities if c not in tools]
        if missing:
            raise PackageError(f"required capabilities not bound: {missing}")
        bindings = RuntimeBindings(tools=tools, predicates=predicates or {}, signatures=self.ir.signatures)
        return lower(self.ir, bindings)

    def as_root(self, tools: dict[str, Any], predicates: dict[str, Any] | None = None,
                *, model_id: str | None = None) -> Root:
        """Wrap the bound tree in a Root so it runs like any authored skill (§40)."""
        root = Root(name=self.manifest.name, child=self.bind(tools, predicates), model_id=model_id)
        return root


def load_package(path: str | Path, *, verify_digests: bool = True) -> LoadedPackage:
    """Load a package directory or `.jdsl` file and verify it structurally."""
    p = Path(path)
    files = _read_zip(p) if p.is_file() else _read_dir(p)

    if "manifest.json" not in files:
        raise PackageError("package has no manifest.json")
    manifest = Manifest.from_dict(json.loads(files["manifest.json"]))
    if manifest.format not in _SUPPORTED_FORMATS:
        raise PackageError(f"unsupported package format {manifest.format!r}")

    if verify_digests:
        _verify_digests(manifest, files)

    if "behavior.json" not in files:
        raise PackageError("package has no behavior.json")
    signatures = _load_signatures(files)
    ir = BehaviorIR.from_dict(json.loads(files["behavior.json"]), signatures)

    report = validate_ir(ir, required_capabilities=set(manifest.required_capabilities))
    if not report.ok:
        raise PackageError("invalid package IR:\n  " + "\n  ".join(report.problems))

    tools = [ToolContract.from_dict(t) for t in json.loads(files.get("tools.json", '{"tools":[]}'))["tools"]]
    prov = [NodeProvenance.from_dict(n)
            for n in json.loads(files.get("provenance.json", '{"nodes":[]}'))["nodes"]]
    return LoadedPackage(manifest=manifest, ir=ir, tools=tools, provenance=prov,
                         root_dir=p if p.is_dir() else None)


def _load_signatures(files: dict[str, str]) -> dict[str, Signature]:
    sigs: dict[str, Signature] = {}
    for name, text in files.items():
        if name.startswith("signatures/") and name.endswith(".json"):
            sig = Signature.from_dict(json.loads(text))
            sigs[sig.id] = sig
    return sigs


def _verify_digests(manifest: Manifest, files: dict[str, str]) -> None:
    for name, expected in manifest.files.items():
        if name == "manifest.json":
            continue
        if name not in files:
            raise PackageError(f"manifest references missing file {name!r}")
        actual = _sha256(files[name])
        if actual != expected:
            raise PackageError(f"digest mismatch for {name!r}: {actual} != {expected}")


def _read_dir(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise PackageError(f"{root} is not a package directory")
    out: dict[str, str] = {}
    for fp in root.rglob("*"):
        if fp.is_file():
            out[fp.relative_to(root).as_posix()] = fp.read_text(encoding="utf-8")
    return out


def _read_zip(path: Path) -> dict[str, str]:
    try:
        with zipfile.ZipFile(path) as zf:
            return {n: zf.read(n).decode("utf-8") for n in zf.namelist()}
    except zipfile.BadZipFile as e:
        raise PackageError(f"{path} is not a valid .jdsl archive") from e


__all__ = ["LoadedPackage", "PackageError", "load_package"]
