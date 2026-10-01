"""Textual authoring workbench for JDSL skills."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static

from jdsl.tui_skill import SkillWorkbench


class SkillApp(App[None]):
    """Author and run restricted JDSL behavior trees."""

    CSS = """
    Screen {
        background: #101417;
        color: #d8e1df;
        layout: vertical;
    }
    Header { background: #17211f; color: #d8e1df; }
    #brand {
        height: 3;
        padding: 0 2;
        background: #182a25;
        border: tall #5ee6a8;
        color: #d8e1df;
        opacity: 0;
    }
    .brand-title { color: #5ee6a8; text-style: bold; }
    .brand-subtitle { color: #9cb2aa; }
    #skill-workspace { height: 1fr; }
    #skill-tree-panel { height: 1fr; }
    #skill-tree-panel > Vertical { width: 2fr; margin-right: 1; }
    #skill-properties-panel { width: 3fr; height: 1fr; padding: 1; background: #141b1a; border: round #2f4d43; }
    #skill-properties-scroll { height: 1fr; }
    #skill-tree { height: 1fr; padding: 1; background: #141b1a; border: round #2f4d43; }
    #skill-properties { height: auto; }
    .field-row { height: 3; }
    .field-row Input { width: 1fr; margin-right: 1; }
    .field-row Input:last-child { margin-right: 0; }
    #skill-properties Label { color: #8da59c; }
    #skill-status { height: 3; padding: 1; color: #bcefd4; background: #0e1314; border: round #2f4d43; }
    .panel-title { color: #5ee6a8; text-style: bold; padding-bottom: 1; }
    .actions { height: auto; padding: 1 0; }
    .actions Button { margin-right: 1; }
    .actions Button.-primary { background: #237a57; }
    Footer { background: #17211f; }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.skill_workbench = SkillWorkbench()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="brand"):
            yield Static("JDSL  /  SKILL AUTHORING WORKBENCH", classes="brand-title")
        yield self.skill_workbench
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#brand").styles.animate("opacity", value=1.0, duration=0.35)


# Kept as an import-compatible name for callers that used the original TUI.
HarnessApp = SkillApp


def run() -> None:
    """Run the JDSL skill authoring workbench."""
    SkillApp().run()


__all__ = ["HarnessApp", "SkillApp", "run"]
