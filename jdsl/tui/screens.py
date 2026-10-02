"""Lifecycle and onboarding screens for the skill workbench."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, Select, Static
from textual.widgets import DirectoryTree


class SavePackageScreen(ModalScreen[dict[str, str] | None]):
    def __init__(self, *, name: str, version: str, description: str, output: str, summary: str) -> None:
        super().__init__()
        self.defaults = (name, version, description, output)
        self.summary = summary

    def compose(self) -> ComposeResult:
        name, version, description, output = self.defaults
        with Vertical(id="save-dialog"):
            yield Static("Save verified behavior package", classes="dialog-title")
            yield Input(value=name, placeholder="Package name", id="save-name")
            yield Input(value=version, placeholder="Version", id="save-version")
            yield Input(value=description, placeholder="Description", id="save-description")
            yield Input(value=output, placeholder="Output path", id="save-output")
            yield Static(self.summary, id="save-summary")
            with Horizontal(classes="actions"):
                yield Button("Export and verify", id="confirm-save", variant="primary")
                yield Button("Cancel", id="cancel-save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "confirm-save":
            self.dismiss(None)
            return
        self.dismiss({
            "name": self.query_one("#save-name", Input).value.strip(),
            "version": self.query_one("#save-version", Input).value.strip(),
            "description": self.query_one("#save-description", Input).value.strip(),
            "output": self.query_one("#save-output", Input).value.strip(),
        })

    def action_cancel(self) -> None:
        self.dismiss(None)


class OpenPackageScreen(ModalScreen[str | None]):
    def __init__(self, start_path: str) -> None:
        super().__init__()
        self.start_path = start_path
        self.selected_path: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="open-dialog"):
            yield Static("Open verified package", classes="dialog-title")
            yield Input(placeholder="Package file or directory", id="open-dialog-path")
            yield DirectoryTree(self.start_path, id="package-tree")
            with Horizontal(classes="actions"):
                yield Button("Open", id="confirm-open", variant="primary")
                yield Button("Cancel", id="cancel-open")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.selected_path = str(event.path)
        self.query_one("#open-dialog-path", Input).value = self.selected_path

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self.selected_path = str(event.path)
        self.query_one("#open-dialog-path", Input).value = self.selected_path

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "confirm-open":
            self.dismiss(None)
            return
        path = self.query_one("#open-dialog-path", Input).value.strip() or self.selected_path
        self.dismiss(path or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class NewTemplateScreen(ModalScreen[str | None]):
    TEMPLATES = [
        ("Blank", "blank"),
        ("Lookup then act", "lookup-act"),
        ("Decide with a model", "predict"),
        ("Guarded write", "guarded-write"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="template-dialog"):
            yield Static("New skill", classes="dialog-title")
            yield Select(self.TEMPLATES, value="blank", id="skill-template")
            with Horizontal(classes="actions"):
                yield Button("Create", id="create-template", variant="primary")
                yield Button("Cancel", id="cancel-template")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "create-template":
            self.dismiss(None)
            return
        value = self.query_one("#skill-template", Select).value
        self.dismiss(str(value))

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static("Workbench shortcuts", classes="dialog-title")
            yield Markdown(
                """| Key | Action |
| --- | --- |
| `Ctrl+S` | Save |
| `Ctrl+O` | Open |
| `Ctrl+N` | New from template |
| `Ctrl+R` | Run |
| `Escape` | Stop run |
| `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / redo |
| `Ctrl+F` | Find a node |
| `Ctrl+Up` / `Ctrl+Down` | Move among siblings |
| `Ctrl+Alt+Left` / `Ctrl+Alt+Right` | Outdent / indent |
| `Ctrl+Shift+D` | Duplicate subtree |
| `Ctrl+P` | Command palette |
| `Ctrl+M` / `Ctrl+G` | Reduced motion / glyphs |

Green nodes are deterministic actions; magenta nodes use model signatures. The
Run panel masks common secret patterns in the final blackboard and never logs
tool arguments or results."""
            )
            yield Button("Close", id="close-help", variant="primary")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class TourScreen(ModalScreen[bool]):
    STEPS = [
        "**Tree**\n\nBuild the behavior on the left. Select a node to edit it; use Add, Move, and the command palette for keyboard-first changes.",
        "**Inspector**\n\nFields follow the selected node type. Structured editors keep refs and schemas explicit, with Raw JSON for advanced expressions.",
        "**State and trust**\n\nValidity, dirty state, and RDB stay visible. Running imports local Python only after you approve that file's content hash.",
    ]

    def __init__(self) -> None:
        super().__init__()
        self.step = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="tour-dialog"):
            yield Static("Skill Workbench tour", classes="dialog-title")
            yield Markdown(self.STEPS[0], id="tour-content")
            with Horizontal(classes="actions"):
                yield Button("Skip", id="skip-tour")
                yield Button("Next", id="next-tour", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "skip-tour":
            self.dismiss(False)
            return
        self.step += 1
        if self.step >= len(self.STEPS):
            self.dismiss(True)
            return
        self.query_one("#tour-content", Markdown).update(self.STEPS[self.step])
        if self.step == len(self.STEPS) - 1:
            self.query_one("#next-tour", Button).label = "Done"

    def action_cancel(self) -> None:
        self.dismiss(False)


__all__ = ["HelpScreen", "NewTemplateScreen", "OpenPackageScreen", "SavePackageScreen", "TourScreen"]