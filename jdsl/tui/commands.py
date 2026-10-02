"""Fuzzy-searchable workbench commands for Textual's command palette."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from functools import partial

from rich.text import Text
from textual.command import DiscoveryHit, Hit, Provider


class WorkbenchCommands(Provider):
    def _commands(self) -> list[tuple[str, Callable[[], None], str]]:
        app = self.app
        workbench = app.skill_workbench
        commands = [
            (f"Add {node_type}", partial(workbench.add_node, node_type), f"Add a {node_type} node")
            for node_type in ("sequence", "selector", "action", "guard", "predict", "react", "repeat")
        ]
        commands.extend([
            ("Validate skill", workbench.validate_skill, "Check the current behavior tree"),
            ("Save skill", workbench.request_save, "Export and verify the current package"),
            ("Open package", workbench.open_skill, "Open a verified .jdsl package"),
            ("Edit definitions", workbench.open_definitions, "Edit tool contracts and inspect signature usage"),
            ("New skill", workbench.request_new_skill, "Start from a skill template"),
            ("Run skill", workbench.run_skill, "Run with the selected trusted tools module"),
            ("Toggle dry run", workbench.toggle_dry_run, "Skip tool execution and show intended calls"),
            ("Undo", workbench.undo, "Undo the last edit"),
            ("Redo", workbench.redo, "Redo the last undone edit"),
            ("Remove node", workbench.remove_selected_node, "Remove the selected subtree"),
            ("Move node up", partial(workbench.move_selected, -1), "Move among siblings"),
            ("Move node down", partial(workbench.move_selected, 1), "Move among siblings"),
            ("Duplicate subtree", workbench.duplicate_selected_node, "Duplicate the selected node and its children"),
            ("Copy subtree", workbench.copy_selected_node, "Copy the selected node and its children"),
            ("Paste subtree", workbench.paste_node, "Paste a copied subtree as a sibling"),
            ("Find node", workbench.focus_search, "Search node IDs and types"),
            ("Help and shortcuts", workbench.show_help, "Open workbench help"),
            ("Open tour", workbench.show_tour, "Review the workbench panels and trust model"),
            ("Toggle reduced motion", app.action_toggle_reduced_motion, "Toggle motion effects"),
            ("Toggle ASCII glyphs", app.action_toggle_glyphs, "Switch between ASCII and Unicode glyphs"),
        ])
        commands.extend(
            (f"Open recent {path}", partial(workbench.open_path, path), "Open a recent verified package")
            for path in app.settings.recent_files
        )
        return commands

    async def discover(self) -> AsyncIterator[DiscoveryHit]:
        for title, callback, description in self._commands():
            yield DiscoveryHit(Text(title), callback, text=title, help=description)

    async def search(self, query: str) -> AsyncIterator[Hit]:
        matcher = self.matcher(query)
        for title, callback, description in self._commands():
            score = matcher.match(title)
            if score is not None:
                yield Hit(score, Text(title), callback, text=title, help=description)


__all__ = ["WorkbenchCommands"]