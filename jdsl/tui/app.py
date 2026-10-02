"""Textual application shell for the skill workbench."""

from __future__ import annotations

import sys

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static

from jdsl.tui.commands import WorkbenchCommands
from jdsl.tui.dialogs import ConfirmDiscardScreen
from jdsl.tui.settings import TUISettings
from jdsl.tui.theme import GRUVBOX_MATERIAL
from jdsl.tui.workbench import SkillWorkbench


class SkillApp(App[None]):
    """Author and run restricted JDSL behavior trees."""

    CSS_PATH = "workbench.tcss"
    COMMANDS = [WorkbenchCommands]
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+s", "save_skill", "Save"),
        ("ctrl+o", "open_skill", "Open"),
        ("ctrl+n", "new_skill", "New"),
        ("ctrl+r", "run_skill", "Run"),
        ("ctrl+f", "find_node", "Find node"),
        ("ctrl+up", "move_up", "Move up"),
        ("ctrl+down", "move_down", "Move down"),
        ("ctrl+alt+left", "outdent_node", "Outdent"),
        ("ctrl+alt+right", "indent_node", "Indent"),
        ("ctrl+shift+d", "duplicate_node", "Duplicate"),
        ("ctrl+shift+c", "copy_node", "Copy subtree"),
        ("ctrl+shift+v", "paste_node", "Paste subtree"),
        ("ctrl+z", "undo", "Undo"),
        ("ctrl+shift+z", "redo", "Redo"),
        ("escape", "stop_run", "Stop run"),
        ("ctrl+m", "toggle_reduced_motion", "Motion"),
        ("ctrl+g", "toggle_glyphs", "Glyphs"),
        ("f1", "help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.register_theme(GRUVBOX_MATERIAL)
        self.theme = GRUVBOX_MATERIAL.name
        self.settings = TUISettings.load()
        self.skill_workbench = SkillWorkbench()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="brand"):
            yield Static("JDSL  /  SKILL AUTHORING WORKBENCH", classes="brand-title")
        yield self.skill_workbench
        yield Footer()

    def on_mount(self) -> None:
        if not self.settings.reduced_motion:
            self.query_one("#brand").styles.animate("opacity", value=1.0, duration=0.35)
        else:
            self.query_one("#brand").styles.opacity = 1.0
        if self.settings.trusted_tools:
            trusted_path = next(reversed(self.settings.trusted_tools))
            self.skill_workbench.query_one("#trusted-tools-state", Static).update(
                f"Trusted tools: {trusted_path}"
            )
        if not self.settings.tour_seen and sys.stdin.isatty():
            self.skill_workbench.show_tour()

    def action_toggle_reduced_motion(self) -> None:
        self.settings.reduced_motion = not self.settings.reduced_motion
        self.settings.save()
        self.skill_workbench.write_status(f"Reduced motion {'on' if self.settings.reduced_motion else 'off'}.")

    def action_toggle_glyphs(self) -> None:
        self.settings.ascii_glyphs = not self.settings.ascii_glyphs
        self.settings.save()
        self.skill_workbench.rebuild_tree()
        self.skill_workbench.write_status(f"ASCII glyphs {'on' if self.settings.ascii_glyphs else 'off'}.")

    def action_undo(self) -> None:
        self.skill_workbench.undo()

    def action_redo(self) -> None:
        self.skill_workbench.redo()

    def action_stop_run(self) -> None:
        self.skill_workbench.cancel_run()

    def action_save_skill(self) -> None:
        self.skill_workbench.request_save()

    def action_open_skill(self) -> None:
        self.skill_workbench.open_skill()

    def action_new_skill(self) -> None:
        self.skill_workbench.request_new_skill()

    def action_run_skill(self) -> None:
        self.skill_workbench.run_skill()

    def action_find_node(self) -> None:
        self.skill_workbench.focus_search()

    def action_help(self) -> None:
        self.skill_workbench.show_help()

    def action_move_up(self) -> None:
        self.skill_workbench.move_selected(-1)

    def action_move_down(self) -> None:
        self.skill_workbench.move_selected(1)

    def action_indent_node(self) -> None:
        self.skill_workbench.indent_selected()

    def action_outdent_node(self) -> None:
        self.skill_workbench.outdent_selected()

    def action_duplicate_node(self) -> None:
        self.skill_workbench.duplicate_selected_node()

    def action_copy_node(self) -> None:
        self.skill_workbench.copy_selected_node()

    def action_paste_node(self) -> None:
        self.skill_workbench.paste_node()

    def action_quit(self) -> None:
        if self.skill_workbench.dirty:
            self.push_screen(ConfirmDiscardScreen(), self._quit_after_confirmation)
        else:
            self.exit()

    def _quit_after_confirmation(self, result: str | None) -> None:
        if result == "discard":
            self.skill_workbench._clear_recovery_file()
            self.exit()


# Kept as an import-compatible name for callers that used the original TUI.
HarnessApp = SkillApp


def run() -> None:
    """Run the JDSL skill authoring workbench."""
    SkillApp().run()


__all__ = ["HarnessApp", "SkillApp", "run"]
