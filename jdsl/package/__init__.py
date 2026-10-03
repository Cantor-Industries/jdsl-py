"""Behavior packages: the portable `.jdsl` artifact — manifest, IR, tool
contracts, signatures, tests, and provenance (design §22, §35 PR13)."""

from jdsl.package.export import (
    BehaviorPackage,
    export_dir,
    export_jdsl,
    package_digest,
)
from jdsl.package.authoring import package_from_root
from jdsl.package.load import LoadedPackage, PackageError, load_package, load_package_object
from jdsl.package.manifest import (
    PACKAGE_FORMAT,
    Manifest,
    NodeProvenance,
    ToolContract,
    ToolEffects,
)
from jdsl.package.proposal import behavior_ir_authoring_guide, package_from_proposal

__all__ = [
    "PACKAGE_FORMAT",
    "Manifest",
    "ToolContract",
    "ToolEffects",
    "NodeProvenance",
    "BehaviorPackage",
    "export_dir",
    "export_jdsl",
    "package_from_root",
    "package_digest",
    "behavior_ir_authoring_guide",
    "package_from_proposal",
    "LoadedPackage",
    "PackageError",
    "load_package",
    "load_package_object",
]
