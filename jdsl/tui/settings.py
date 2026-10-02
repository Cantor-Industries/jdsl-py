"""Persist small, user-facing workbench preferences."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class TUISettings:
    reduced_motion: bool = False
    ascii_glyphs: bool = True
    trusted_tools: dict[str, str] = field(default_factory=dict)
    recent_files: list[str] = field(default_factory=list)
    tour_seen: bool = False

    @classmethod
    def load(cls) -> TUISettings:
        path = settings_path()
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(values, dict):
            return cls()
        trusted_tools = values.get("trusted_tools", {})
        if not isinstance(trusted_tools, dict):
            trusted_tools = {}
        recent_files = values.get("recent_files", [])
        if not isinstance(recent_files, list):
            recent_files = []
        return cls(
            reduced_motion=bool(values.get("reduced_motion", False)),
            ascii_glyphs=bool(values.get("ascii_glyphs", True)),
            trusted_tools=dict(trusted_tools),
            recent_files=[str(path) for path in recent_files],
            tour_seen=bool(values.get("tour_seen", False)),
        )

    def save(self) -> None:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")


def settings_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "jdsl" / "tui.json"


def recovery_path() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "jdsl" / "tui-recovery.json"


__all__ = ["TUISettings", "recovery_path", "settings_path"]
