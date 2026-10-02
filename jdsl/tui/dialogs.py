"""Small modal screens used by the authoring workbench."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class TrustToolsScreen(ModalScreen[bool]):
    """Confirm that a local tools module may execute as Python code."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, path: str, digest: str) -> None:
        super().__init__()
        self.path = path
        self.digest = digest

    def compose(self) -> ComposeResult:
        with Vertical(id="trust-dialog"):
            yield Static("Run imports and executes this local Python module.", classes="dialog-title")
            yield Static(self.path, id="trust-path")
            yield Static(f"Content SHA-256: {self.digest[:16]}…", id="trust-digest")
            with Horizontal(classes="actions"):
                yield Button("Trust this version", id="trust-tools", variant="primary")
                yield Button("Cancel", id="cancel-trust")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "trust-tools")

    def action_cancel(self) -> None:
        self.dismiss(False)


class ConfirmDiscardScreen(ModalScreen[str]):
    """Prevent open, new, and quit actions from silently losing edits."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="trust-dialog"):
            yield Static("This skill has unsaved changes.", classes="dialog-title")
            with Horizontal(classes="actions"):
                yield Button("Discard changes", id="discard-changes", variant="error")
                yield Button("Keep editing", id="cancel-discard")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss("discard" if event.button.id == "discard-changes" else "cancel")

    def action_cancel(self) -> None:
        self.dismiss("cancel")


__all__ = ["ConfirmDiscardScreen", "TrustToolsScreen"]
