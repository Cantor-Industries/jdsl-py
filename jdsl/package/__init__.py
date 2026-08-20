"""Behavior packages: the portable `.jdslpkg` artifact — manifest, IR, tool
contracts, signatures, tests, and provenance (design §22, §35 PR13)."""

from jdsl.package.export import (
    BehaviorPackage,
    export_dir,
    export_jdslpkg,
    package_digest,
)
from jdsl.package.load import LoadedPackage, PackageError, load_package
from jdsl.package.manifest import (
    PACKAGE_FORMAT,
    Manifest,
    NodeProvenance,
    ToolContract,
    ToolEffects,
)

__all__ = [
    "PACKAGE_FORMAT",
    "Manifest",
    "ToolContract",
    "ToolEffects",
    "NodeProvenance",
    "BehaviorPackage",
    "export_dir",
    "export_jdslpkg",
    "package_digest",
    "LoadedPackage",
    "PackageError",
    "load_package",
]
