"""Behavior-package metadata: manifest, tool contracts, and provenance
(design §12, §22.2, §23).

A `.jdsl` is executable policy, so its metadata is first-class: the manifest
declares required capabilities and verification status, tool contracts give each
capability a portable logical identity and effect flags, and provenance answers
"why does this node exist?" for audit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PACKAGE_FORMAT = "jdsl.package.v1"


@dataclass
class ToolEffects:
    """Effect flags for a capability (§12). Third-party MCP annotations are hints;
    critical properties should be contract-backed (§12, §15 E3)."""
    read_only: bool = True
    destructive: bool = False
    idempotent: bool = True


@dataclass
class ToolContract:
    """A portable capability contract (§12): logical id + schemas + effects. Host
    tool names (`mcp__retail__get_order`) bind to this logical id at runtime."""
    logical_id: str
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    output_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    effects: ToolEffects = field(default_factory=ToolEffects)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_id": self.logical_id,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "effects": asdict(self.effects),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolContract:
        eff = data.get("effects", {})
        return cls(
            logical_id=data["logical_id"],
            input_schema=data.get("input_schema", {"type": "object"}),
            output_schema=data.get("output_schema", {"type": "object"}),
            effects=ToolEffects(read_only=eff.get("read_only", True),
                                destructive=eff.get("destructive", False),
                                idempotent=eff.get("idempotent", True)),
            description=data.get("description", ""),
        )


@dataclass
class NodeProvenance:
    """Why a compiled node exists (§23) — traceable back to source evidence."""
    node_id: str
    behavior_candidate: str | None = None
    evidence_grade: str = "E0"
    source_episodes: list[str] = field(default_factory=list)
    contract_sources: list[str] = field(default_factory=list)
    compiler_model: str | None = None
    rationale_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeProvenance:
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__ if k in data})


@dataclass
class Manifest:
    """Package manifest (§22.2)."""
    name: str
    version: str = "0.1.0"
    task_family: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    runtime: dict[str, str] = field(default_factory=lambda: {"jdsl": ">=0.3"})
    source: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=lambda: {"status": "unverified"})
    files: dict[str, str] = field(default_factory=dict)
    format: str = PACKAGE_FORMAT

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "name": self.name,
            "version": self.version,
            "task_family": self.task_family,
            "runtime": self.runtime,
            "required_capabilities": self.required_capabilities,
            "source": self.source,
            "verification": self.verification,
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        return cls(
            name=data["name"], version=data.get("version", "0.1.0"),
            task_family=data.get("task_family", ""),
            required_capabilities=data.get("required_capabilities", []),
            runtime=data.get("runtime", {"jdsl": ">=0.3"}),
            source=data.get("source", {}), verification=data.get("verification", {"status": "unverified"}),
            files=data.get("files", {}), format=data.get("format", PACKAGE_FORMAT),
        )


__all__ = ["PACKAGE_FORMAT", "ToolEffects", "ToolContract", "NodeProvenance", "Manifest"]
