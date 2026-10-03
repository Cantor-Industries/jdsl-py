"""Generated run-input fields with an escape hatch for larger input sets."""

from __future__ import annotations

import json
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static, TabPane, TabbedContent, TextArea


class RunInputsEditor(Vertical):
    ROW_COUNT = 12

    def compose(self) -> ComposeResult:
        with TabbedContent(id="run-input-tabs"):
            with TabPane("Fields", id="run-input-fields-pane"):
                with Vertical(id="run-input-rows"):
                    for index in range(self.ROW_COUNT):
                        with Horizontal(classes="run-input-row", id=f"run-input-row-{index}"):
                            yield Input(placeholder="Input name / ref path", id=f"run-input-name-{index}")
                            yield Input(placeholder="Value (JSON or text)", id=f"run-input-value-{index}")
                            yield Button("Remove", id=f"run-input-remove-{index}")
                yield Button("Add input", id="run-input-add")
            with TabPane("Raw JSON", id="run-input-raw-pane"):
                yield TextArea("{}", id="run-inputs-raw")
                yield Static("", id="run-input-error", classes="editor-error")

    def on_mount(self) -> None:
        for index in range(self.ROW_COUNT):
            self._row(index).styles.display = "none"

    def load(self, required: list[str], saved_values: dict[str, Any] | None = None) -> None:
        try:
            previous = self.value()
        except ValueError:
            previous = {}
        saved_values = saved_values or {}
        values = {
            name: previous[name] if name in previous else saved_values[name]
            for name in required if name in previous or name in saved_values
        }
        for index in range(self.ROW_COUNT):
            name = required[index] if index < len(required) else ""
            row = self._row(index)
            row.styles.display = "block" if name else "none"
            self.query_one(f"#run-input-name-{index}", Input).value = name
            value = values.get(name, "")
            self.query_one(f"#run-input-value-{index}", Input).value = self._display(value)
        self.query_one("#run-inputs-raw", TextArea).load_text(json.dumps(values, sort_keys=True, indent=2))
        tabs = self.query_one("#run-input-tabs", TabbedContent)
        tabs.active = "run-input-fields-pane"
        if len(required) > self.ROW_COUNT:
            self.query_one("#run-input-error", Static).update(
                "More than 12 inputs are required; use Raw JSON to provide all values."
            )
            tabs.active = "run-input-raw-pane"

    def value(self) -> dict[str, Any]:
        if self.query_one("#run-input-tabs", TabbedContent).active == "run-input-raw-pane":
            try:
                values = json.loads(self.query_one("#run-inputs-raw", TextArea).text or "{}")
            except json.JSONDecodeError as error:
                self.query_one("#run-input-error", Static).update(f"Invalid JSON: {error.msg}")
                raise ValueError(f"run inputs JSON: {error.msg}") from error
            if not isinstance(values, dict):
                raise ValueError("run inputs must be a JSON object")
            self.query_one("#run-input-error", Static).update("")
            return values

        values: dict[str, Any] = {}
        for index in range(self.ROW_COUNT):
            if self._row(index).styles.display == "none":
                continue
            name = self.query_one(f"#run-input-name-{index}", Input).value.strip()
            if not name:
                continue
            if name in values:
                raise ValueError(f"duplicate run input {name!r}")
            raw = self.query_one(f"#run-input-value-{index}", Input).value
            try:
                values[name] = json.loads(raw)
            except json.JSONDecodeError:
                values[name] = raw
        self.query_one("#run-inputs-raw", TextArea).load_text(json.dumps(values, sort_keys=True, indent=2))
        return values

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-input-add":
            index = next((i for i in range(self.ROW_COUNT) if self._row(i).styles.display == "none"), None)
            if index is None:
                self.query_one("#run-input-error", Static).update(
                    "Input field limit reached; use Raw JSON for more values."
                )
                return
            self._row(index).styles.display = "block"
            self.query_one(f"#run-input-name-{index}", Input).focus()
        elif event.button.id and event.button.id.startswith("run-input-remove-"):
            index = int(event.button.id.rsplit("-", 1)[1])
            self.query_one(f"#run-input-name-{index}", Input).value = ""
            self.query_one(f"#run-input-value-{index}", Input).value = ""
            self._row(index).styles.display = "none"

    def _row(self, index: int) -> Horizontal:
        return self.query_one(f"#run-input-row-{index}", Horizontal)

    @staticmethod
    def _display(value: Any) -> str:
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


__all__ = ["RunInputsEditor"]