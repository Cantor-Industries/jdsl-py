"""Structured editors for action values and safe guard expressions."""

from __future__ import annotations

import json
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input, Select, Static, TabPane, TabbedContent, TextArea

from jdsl.ir.expr import validate_expr


class ArgumentsChanged(Message):
    """An action argument changed in either editor tab."""


class GuardChanged(Message):
    """A guard expression changed in either editor tab."""


class ActionArgumentsEditor(Vertical):
    ROW_COUNT = 12
    VALUE_KINDS = [
        ("Literal", "literal"),
        ("Run input", "input"),
        ("Exact ref", "ref"),
        ("Dynamic ref", "dynamic"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._loading = False
        self._last_state: tuple[Any, ...] | None = None

    def compose(self) -> ComposeResult:
        with TabbedContent(id="arguments-tabs"):
            with TabPane("Structured", id="arguments-structured"):
                yield Static("Name                 Kind         Value", classes="table-heading")
                with Vertical(id="argument-rows"):
                    for index in range(self.ROW_COUNT):
                        with Horizontal(classes="argument-row", id=f"argument-row-{index}"):
                            yield Input(placeholder="Argument", id=f"argument-name-{index}")
                            yield Select(self.VALUE_KINDS, value="literal", id=f"argument-kind-{index}")
                            yield Input(placeholder="Value or ref path", id=f"argument-value-{index}")
                            yield Static("Exact ref", classes="argument-ref-tag", id=f"argument-ref-{index}")
                            yield Button("Remove", id=f"argument-remove-{index}")
                yield Static("", id="argument-editor-error", classes="editor-error")
                yield Button("Add argument", id="argument-add")
            with TabPane("Raw JSON", id="arguments-raw-pane"):
                yield TextArea("{}", id="node-arguments-raw")
                yield Static("", id="argument-raw-error", classes="editor-error")

    def on_mount(self) -> None:
        for index in range(self.ROW_COUNT):
            self._row(index).styles.display = "none"
            self.query_one(f"#argument-ref-{index}", Static).styles.display = "none"

    def load(self, arguments: dict[str, Any]) -> None:
        self._loading = True
        try:
            raw = json.dumps(arguments, sort_keys=True, indent=2)
            self._set_text("node-arguments-raw", raw)
            self.query_one("#argument-raw-error", Static).update("")
            self.query_one("#argument-editor-error", Static).update("")
            entries = list(arguments.items())
            for index in range(self.ROW_COUNT):
                row = self._row(index)
                if index >= len(entries):
                    self._set_input(f"argument-name-{index}", "")
                    self._set_input(f"argument-value-{index}", "")
                    self._set_select(f"argument-kind-{index}", "literal")
                    row.styles.display = "none"
                    continue
                name, spec = entries[index]
                kind, value = self._decode_value(spec)
                self._set_input(f"argument-name-{index}", str(name))
                self._set_select(f"argument-kind-{index}", kind)
                self._set_input(f"argument-value-{index}", value)
                row.styles.display = "block"
                self._update_ref_tag(index, kind)
            self.query_one("#arguments-tabs", TabbedContent).active = "arguments-structured"
            if len(entries) > self.ROW_COUNT:
                self.query_one("#argument-editor-error", Static).update(
                    f"{len(entries)} arguments exceed the structured editor limit; use Raw JSON to preserve all."
                )
                self.query_one("#arguments-tabs", TabbedContent).active = "arguments-raw-pane"
        finally:
            self._loading = False
        self._last_state = self._snapshot()

    def value(self) -> dict[str, Any]:
        tabs = self.query_one("#arguments-tabs", TabbedContent)
        if tabs.active == "arguments-raw-pane":
            try:
                value = json.loads(self.query_one("#node-arguments-raw", TextArea).text or "{}")
            except json.JSONDecodeError as error:
                self.query_one("#argument-raw-error", Static).update(f"Invalid JSON: {error.msg}")
                raise ValueError(f"arguments JSON: {error.msg}") from error
            if not isinstance(value, dict):
                raise ValueError("action arguments must be a JSON object")
            self.query_one("#argument-raw-error", Static).update("")
            return value

        result: dict[str, Any] = {}
        for index in range(self.ROW_COUNT):
            if self._row(index).styles.display == "none":
                continue
            name = self.query_one(f"#argument-name-{index}", Input).value.strip()
            if not name:
                continue
            if name in result:
                raise ValueError(f"duplicate argument name {name!r}")
            kind = str(self.query_one(f"#argument-kind-{index}", Select).value)
            raw_value = self.query_one(f"#argument-value-{index}", Input).value.strip()
            if kind in {"input", "ref", "dynamic"}:
                if not raw_value:
                    raise ValueError(f"argument {name!r} needs a ref path")
                result[name] = {"ref": raw_value}
            else:
                try:
                    result[name] = {"const": json.loads(raw_value)}
                except json.JSONDecodeError:
                    result[name] = {"const": raw_value}
        self._sync_raw(result)
        self.query_one("#argument-editor-error", Static).update("")
        self._last_state = self._snapshot()
        return result

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "node-arguments-raw":
            return
        self._changed(event.input.id)

    def on_select_changed(self, event: Select.Changed) -> None:
        self._changed(event.select.id)
        if event.select.id and event.select.id.startswith("argument-kind-"):
            self._update_ref_tag(int(event.select.id.rsplit("-", 1)[1]), str(event.value))

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id != "node-arguments-raw":
            return
        self._changed(event.text_area.id)
        try:
            parsed = json.loads(event.text_area.text or "{}")
            error = "" if isinstance(parsed, dict) else "Arguments must be a JSON object."
        except json.JSONDecodeError as exception:
            error = f"Invalid JSON: {exception.msg}"
        self.query_one("#argument-raw-error", Static).update(error)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "argument-add":
            index = next((i for i in range(self.ROW_COUNT) if self._row(i).styles.display == "none"), None)
            if index is None:
                self.query_one("#argument-editor-error", Static).update(
                    "Structured editor limit reached; use Raw JSON for more arguments."
                )
                return
            self._row(index).styles.display = "block"
            self.query_one(f"#argument-name-{index}", Input).focus()
            self.post_message(ArgumentsChanged())
            return
        if event.button.id and event.button.id.startswith("argument-remove-"):
            index = int(event.button.id.rsplit("-", 1)[1])
            self._set_input(f"argument-name-{index}", "")
            self._set_input(f"argument-value-{index}", "")
            self._row(index).styles.display = "none"
            self.post_message(ArgumentsChanged())

    def _changed(self, _widget_id: str | None = None) -> None:
        if self._loading:
            return
        state = self._snapshot()
        if state == self._last_state:
            return
        self._last_state = state
        self.post_message(ArgumentsChanged())

    def _snapshot(self) -> tuple[Any, ...]:
        values: list[Any] = [self.query_one("#arguments-tabs", TabbedContent).active]
        values.append(self.query_one("#node-arguments-raw", TextArea).text)
        for index in range(self.ROW_COUNT):
            values.extend((
                self._row(index).styles.display,
                self.query_one(f"#argument-name-{index}", Input).value,
                self.query_one(f"#argument-kind-{index}", Select).value,
                self.query_one(f"#argument-value-{index}", Input).value,
            ))
        return tuple(values)

    def _row(self, index: int) -> Horizontal:
        return self.query_one(f"#argument-row-{index}", Horizontal)

    def _decode_value(self, value: Any) -> tuple[str, str]:
        if isinstance(value, dict) and set(value) == {"ref"}:
            path = str(value["ref"])
            kind = "dynamic" if "[$" in path else "ref"
            return kind, path
        if isinstance(value, dict) and set(value) == {"const"}:
            value = value["const"]
        return "literal", json.dumps(value, ensure_ascii=False)

    def _update_ref_tag(self, index: int, kind: str) -> None:
        tag = self.query_one(f"#argument-ref-{index}", Static)
        tag.styles.display = "block" if kind in {"input", "ref", "dynamic"} else "none"

    def _set_input(self, widget_id: str, value: str) -> None:
        widget = self.query_one(f"#{widget_id}", Input)
        widget.value = value

    def _set_select(self, widget_id: str, value: str) -> None:
        widget = self.query_one(f"#{widget_id}", Select)
        widget.value = value

    def _set_text(self, widget_id: str, value: str) -> None:
        widget = self.query_one(f"#{widget_id}", TextArea)
        widget.load_text(value)

    def _sync_raw(self, value: dict[str, Any]) -> None:
        self._set_text("node-arguments-raw", json.dumps(value, sort_keys=True, indent=2))


class GuardExpressionEditor(Vertical):
    OPERATORS = [
        ("Exists", "exists"),
        ("Equals", "eq"),
        ("Not equals", "neq"),
        ("Less than", "lt"),
        ("At most", "lte"),
        ("Greater than", "gt"),
        ("At least", "gte"),
        ("In", "in"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._loading = False
        self._last_state: tuple[Any, ...] | None = None

    def compose(self) -> ComposeResult:
        with TabbedContent(id="guard-tabs"):
            with TabPane("Builder", id="guard-builder-pane"):
                yield Select(self.OPERATORS, value="eq", id="guard-operator")
                with Horizontal(classes="guard-operands"):
                    yield Input(placeholder="Blackboard path", id="guard-left")
                    yield Select([("Literal", "literal"), ("Ref", "ref")], value="literal", id="guard-right-kind")
                    yield Input(placeholder="JSON literal or ref path", id="guard-right")
                yield Static("", id="guard-preview")
                yield Static("", id="guard-builder-error", classes="editor-error")
            with TabPane("Raw JSON", id="guard-raw-pane"):
                yield TextArea("{}", id="node-expression-raw")
                yield Static("", id="guard-raw-error", classes="editor-error")

    def load(self, expression: dict[str, Any]) -> None:
        self._loading = True
        try:
            self._set_text("node-expression-raw", json.dumps(expression, sort_keys=True, indent=2))
            self.query_one("#guard-raw-error", Static).update("")
            supported = self._load_builder(expression)
            self.query_one("#guard-tabs", TabbedContent).active = (
                "guard-builder-pane" if supported else "guard-raw-pane"
            )
            self._update_builder()
        finally:
            self._loading = False
        self._last_state = self._snapshot()

    def value(self) -> dict[str, Any]:
        if self.query_one("#guard-tabs", TabbedContent).active == "guard-raw-pane":
            try:
                expression = json.loads(self.query_one("#node-expression-raw", TextArea).text or "{}")
            except json.JSONDecodeError as error:
                self.query_one("#guard-raw-error", Static).update(f"Invalid JSON: {error.msg}")
                raise ValueError(f"guard JSON: {error.msg}") from error
        else:
            expression = self._build_expression()
        problems = validate_expr(expression)
        if problems:
            message = "; ".join(problems)
            self.query_one("#guard-builder-error", Static).update(message)
            raise ValueError(message)
        self._sync_raw(expression)
        self.query_one("#guard-builder-error", Static).update("")
        self.query_one("#guard-raw-error", Static).update("")
        self._last_state = self._snapshot()
        return expression

    def on_input_changed(self, event: Input.Changed) -> None:
        self._changed(event.input.id)
        self._update_builder()

    def on_select_changed(self, event: Select.Changed) -> None:
        self._changed(event.select.id)
        self._update_builder()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id != "node-expression-raw":
            return
        self._changed(event.text_area.id)
        self._validate_raw(event.text_area.text)

    def _load_builder(self, expression: dict[str, Any]) -> bool:
        if not isinstance(expression, dict) or len(expression) != 1:
            return False
        operator, value = next(iter(expression.items()))
        if operator == "exists":
            left = value.get("ref") if isinstance(value, dict) else value
            if not isinstance(left, str):
                return False
            self._set_select("guard-operator", "exists")
            self._set_input("guard-left", left)
            self._set_select("guard-right-kind", "literal")
            self._set_input("guard-right", "")
            return True
        if operator not in {"eq", "neq", "lt", "lte", "gt", "gte", "in"}:
            return False
        if not isinstance(value, list) or len(value) != 2:
            return False
        left, right = value
        if not isinstance(left, dict) or set(left) != {"ref"}:
            return False
        self._set_select("guard-operator", operator)
        self._set_input("guard-left", str(left["ref"]))
        if isinstance(right, dict) and set(right) == {"ref"}:
            self._set_select("guard-right-kind", "ref")
            self._set_input("guard-right", str(right["ref"]))
        elif isinstance(right, dict) and set(right) == {"const"}:
            self._set_select("guard-right-kind", "literal")
            self._set_input("guard-right", json.dumps(right["const"], ensure_ascii=False))
        else:
            self._set_select("guard-right-kind", "literal")
            self._set_input("guard-right", json.dumps(right, ensure_ascii=False))
        return True

    def _build_expression(self) -> dict[str, Any]:
        operator = str(self.query_one("#guard-operator", Select).value)
        left = self.query_one("#guard-left", Input).value.strip()
        if not left:
            raise ValueError("enter a blackboard path")
        if operator == "exists":
            return {"exists": left}
        raw_right = self.query_one("#guard-right", Input).value.strip()
        if str(self.query_one("#guard-right-kind", Select).value) == "ref":
            if not raw_right:
                raise ValueError("enter a right-side ref path")
            right: Any = {"ref": raw_right}
        else:
            if not raw_right:
                raise ValueError("enter a right-side literal")
            try:
                right = json.loads(raw_right)
            except json.JSONDecodeError:
                right = raw_right
        return {operator: [{"ref": left}, right]}

    def _update_builder(self) -> None:
        if not self.is_mounted:
            return
        operator = str(self.query_one("#guard-operator", Select).value)
        right_kind = self.query_one("#guard-right-kind", Select)
        right_value = self.query_one("#guard-right", Input)
        right_kind.styles.display = "none" if operator == "exists" else "block"
        right_value.styles.display = "none" if operator == "exists" else "block"
        try:
            expression = self._build_expression()
            preview = json.dumps(expression, ensure_ascii=False, separators=(",", ": "))
            problems = validate_expr(expression)
            self.query_one("#guard-preview", Static).update(f"Preview: {preview}")
            self.query_one("#guard-builder-error", Static).update("; ".join(problems))
        except ValueError as error:
            self.query_one("#guard-preview", Static).update("Preview unavailable")
            self.query_one("#guard-builder-error", Static).update(str(error))

    def _validate_raw(self, text: str) -> None:
        try:
            expression = json.loads(text or "{}")
        except json.JSONDecodeError as error:
            self.query_one("#guard-raw-error", Static).update(f"Invalid JSON: {error.msg}")
            return
        problems = validate_expr(expression)
        self.query_one("#guard-raw-error", Static).update("; ".join(problems))

    def _changed(self, _widget_id: str | None) -> None:
        if self._loading:
            return
        state = self._snapshot()
        if state == self._last_state:
            return
        self._last_state = state
        self.post_message(GuardChanged())

    def _snapshot(self) -> tuple[Any, ...]:
        return (
            self.query_one("#guard-tabs", TabbedContent).active,
            self.query_one("#guard-operator", Select).value,
            self.query_one("#guard-left", Input).value,
            self.query_one("#guard-right-kind", Select).value,
            self.query_one("#guard-right", Input).value,
            self.query_one("#node-expression-raw", TextArea).text,
        )

    def _set_input(self, widget_id: str, value: str) -> None:
        widget = self.query_one(f"#{widget_id}", Input)
        widget.value = value

    def _set_select(self, widget_id: str, value: str) -> None:
        widget = self.query_one(f"#{widget_id}", Select)
        widget.value = value

    def _set_text(self, widget_id: str, value: str) -> None:
        widget = self.query_one(f"#{widget_id}", TextArea)
        widget.load_text(value)

    def _sync_raw(self, expression: dict[str, Any]) -> None:
        self._set_text("node-expression-raw", json.dumps(expression, sort_keys=True, indent=2))


__all__ = ["ActionArgumentsEditor", "ArgumentsChanged", "GuardChanged", "GuardExpressionEditor"]