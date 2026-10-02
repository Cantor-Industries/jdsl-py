"""Authoring controls for reusable predict/react signatures."""

from __future__ import annotations

import json
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import (
    Button,
    Collapsible,
    Input,
    SelectionList,
    Static,
    TabPane,
    TabbedContent,
    TextArea,
)

from jdsl.ir.schema import Signature, SignatureInput, SignatureOutput
from jdsl.tree import render_signature_prompt


class SignatureChanged(Message):
    """A signature field was edited."""


class SignatureEditor(Vertical):
    INPUT_COUNT = 8

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._loading = False
        self._last_state: tuple[Any, ...] | None = None
        self._kind = "predict"

    def compose(self) -> ComposeResult:
        yield Static("Inputs", classes="table-heading")
        with TabbedContent(id="signature-input-tabs"):
            with TabPane("Structured", id="signature-input-structured"):
                yield Static("Alias                 Source path                 Schema JSON", classes="table-heading")
                with Vertical(id="signature-input-rows"):
                    for index in range(self.INPUT_COUNT):
                        with Horizontal(classes="signature-input-row", id=f"signature-input-row-{index}"):
                            yield Input(placeholder="Alias", id=f"signature-alias-{index}")
                            yield Input(placeholder="Blackboard source path", id=f"signature-source-{index}")
                            yield Input(value='{"type":"string"}', id=f"signature-schema-{index}")
                            yield Button("Remove", id=f"signature-input-remove-{index}")
                yield Static("", id="signature-input-error", classes="editor-error")
                yield Button("Add input", id="signature-input-add")
            with TabPane("Raw JSON", id="signature-input-raw-pane"):
                yield TextArea("{}", id="signature-inputs-raw")
                yield Static("", id="signature-input-raw-error", classes="editor-error")
        yield Input(placeholder="Output name", id="signature-output-name")
        yield TextArea('{"type":"string"}', id="signature-output-schema")
        yield TextArea("", id="signature-instruction")
        yield Static("0 characters", id="signature-char-count")
        yield Static("Allowed tools", id="signature-tools-heading")
        yield SelectionList(id="signature-tools-list")
        with Collapsible(title="Examples, validator, and context policy", collapsed=True, id="signature-advanced"):
            yield Static("Examples JSON", classes="field-label")
            yield TextArea("[]", id="signature-examples")
            yield Static("Validator JSON", classes="field-label")
            yield TextArea('{"type":"json_schema"}', id="signature-validator")
            yield Static("Context policy JSON", classes="field-label")
            yield TextArea("{}", id="signature-context-policy")
        yield Static("Prompt preview", classes="field-label")
        yield Static("", id="signature-preview")
        yield Static("", id="signature-editor-error", classes="editor-error")

    def on_mount(self) -> None:
        for index in range(self.INPUT_COUNT):
            self._row(index).styles.display = "none"

    def load(self, signature: Signature | None, available_tools: list[str], kind: str) -> None:
        self._loading = True
        try:
            self._kind = kind
            if signature is None:
                inputs: dict[str, SignatureInput] = {}
                output = SignatureOutput(name="answer")
                instruction = ""
                examples: list[dict[str, Any]] = []
                validator = {"type": "json_schema"}
                context_policy: dict[str, Any] = {}
                tools: list[str] = []
            else:
                inputs = signature.inputs
                output = signature.output or SignatureOutput(name="answer")
                instruction = signature.instruction
                examples = signature.examples
                validator = signature.validator
                context_policy = signature.context_policy
                tools = signature.tools

            entries = list(inputs.items())
            raw_inputs = {
                alias: {"source": item.source, "schema": item.schema}
                for alias, item in entries
            }
            self._set_text("signature-inputs-raw", json.dumps(raw_inputs, sort_keys=True, indent=2))
            self._set_input("signature-output-name", output.name)
            self._set_text("signature-output-schema", json.dumps(output.schema, sort_keys=True, indent=2))
            self._set_text("signature-instruction", instruction)
            self._set_text("signature-examples", json.dumps(examples, sort_keys=True, indent=2))
            self._set_text("signature-validator", json.dumps(validator, sort_keys=True, indent=2))
            self._set_text("signature-context-policy", json.dumps(context_policy, sort_keys=True, indent=2))
            self.query_one("#signature-input-error", Static).update("")
            self.query_one("#signature-input-raw-error", Static).update("")
            self.query_one("#signature-editor-error", Static).update("")

            for index in range(self.INPUT_COUNT):
                row = self._row(index)
                if index >= len(entries):
                    self._set_input(f"signature-alias-{index}", "")
                    self._set_input(f"signature-source-{index}", "")
                    self._set_input(f"signature-schema-{index}", '{"type":"string"}')
                    row.styles.display = "none"
                    continue
                alias, item = entries[index]
                self._set_input(f"signature-alias-{index}", alias)
                self._set_input(f"signature-source-{index}", item.source)
                self._set_input(f"signature-schema-{index}", json.dumps(item.schema, sort_keys=True))
                row.styles.display = "block"
            self.query_one("#signature-input-tabs", TabbedContent).active = "signature-input-structured"
            if len(entries) > self.INPUT_COUNT:
                self.query_one("#signature-input-error", Static).update(
                    "Too many inputs for the structured editor; Raw JSON preserves all entries."
                )
                self.query_one("#signature-input-tabs", TabbedContent).active = "signature-input-raw-pane"

            tool_list = self.query_one("#signature-tools-list", SelectionList)
            tool_list.clear_options()
            for tool in sorted(set(available_tools) | set(tools)):
                tool_list.add_option((tool, tool, tool in tools))
            self.query_one("#signature-tools-heading", Static).styles.display = "block" if kind == "react" else "none"
            tool_list.styles.display = "block" if kind == "react" else "none"
        finally:
            self._loading = False
        self._update_instruction_count()
        self._update_preview()
        self._last_state = self._snapshot()

    def value(self, kind: str) -> dict[str, Any]:
        if self.query_one("#signature-input-tabs", TabbedContent).active == "signature-input-raw-pane":
            try:
                raw_inputs = json.loads(self.query_one("#signature-inputs-raw", TextArea).text or "{}")
            except json.JSONDecodeError as error:
                raise ValueError(f"signature inputs JSON: {error.msg}") from error
            if not isinstance(raw_inputs, dict):
                raise ValueError("signature inputs must be a JSON object")
            inputs = {
                str(alias): SignatureInput(
                    source=str(spec.get("source", alias)),
                    schema=spec.get("schema", {"type": "string"}),
                )
                for alias, spec in raw_inputs.items()
                if isinstance(spec, dict)
            }
            if len(inputs) != len(raw_inputs):
                raise ValueError("each signature input must have a source/schema object")
        else:
            inputs = {}
            for index in range(self.INPUT_COUNT):
                if self._row(index).styles.display == "none":
                    continue
                alias = self.query_one(f"#signature-alias-{index}", Input).value.strip()
                source = self.query_one(f"#signature-source-{index}", Input).value.strip()
                schema_text = self.query_one(f"#signature-schema-{index}", Input).value.strip()
                if not alias and not source:
                    continue
                if not alias or not source:
                    raise ValueError("each signature input needs both an alias and a source path")
                if alias in inputs:
                    raise ValueError(f"duplicate signature input alias {alias!r}")
                try:
                    schema = json.loads(schema_text or '{"type":"string"}')
                except json.JSONDecodeError as error:
                    raise ValueError(f"schema for {alias!r}: {error.msg}") from error
                if not isinstance(schema, dict):
                    raise ValueError(f"schema for {alias!r} must be a JSON object")
                inputs[alias] = SignatureInput(source=source, schema=schema)
            self._sync_raw_inputs(inputs)

        output_name = self.query_one("#signature-output-name", Input).value.strip() or "answer"
        output_schema = self._json_object("signature-output-schema", "output schema")
        examples = self._json_value("signature-examples", "examples")
        context_policy = self._json_object("signature-context-policy", "context policy")
        validator = self._json_object("signature-validator", "validator")
        if not isinstance(examples, list):
            raise ValueError("examples must be a JSON array")
        tools = list(self.query_one("#signature-tools-list", SelectionList).selected) if kind == "react" else []
        return {
            "inputs": inputs,
            "output": SignatureOutput(name=output_name, schema=output_schema),
            "instruction": self.query_one("#signature-instruction", TextArea).text,
            "examples": examples,
            "context_policy": context_policy,
            "validator": validator,
            "tools": tools,
        }

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._changed(event.input.id):
            self._update_preview()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._changed(event.text_area.id):
            if event.text_area.id == "signature-instruction":
                self._update_instruction_count()
            self._update_preview()

    def on_selection_list_selection_toggled(self, _event: SelectionList.SelectionToggled) -> None:
        if not self._loading:
            self._changed(None)
            self._update_preview()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "signature-input-add":
            index = next((i for i in range(self.INPUT_COUNT) if self._row(i).styles.display == "none"), None)
            if index is None:
                self.query_one("#signature-input-error", Static).update(
                    "Structured input limit reached; use Raw JSON for more inputs."
                )
                return
            self._row(index).styles.display = "block"
            self.query_one(f"#signature-alias-{index}", Input).focus()
            self._changed(None)
        elif event.button.id and event.button.id.startswith("signature-input-remove-"):
            index = int(event.button.id.rsplit("-", 1)[1])
            self._set_input(f"signature-alias-{index}", "")
            self._set_input(f"signature-source-{index}", "")
            self._row(index).styles.display = "none"
            self._changed(None)

    def _changed(self, _widget_id: str | None) -> bool:
        if self._loading:
            return False
        state = self._snapshot()
        if state == self._last_state:
            return False
        self._last_state = state
        self.post_message(SignatureChanged())
        return True

    def _snapshot(self) -> tuple[Any, ...]:
        values: list[Any] = [
            self.query_one("#signature-input-tabs", TabbedContent).active,
            self.query_one("#signature-inputs-raw", TextArea).text,
            self.query_one("#signature-output-name", Input).value,
            self.query_one("#signature-output-schema", TextArea).text,
            self.query_one("#signature-instruction", TextArea).text,
            self.query_one("#signature-examples", TextArea).text,
            self.query_one("#signature-validator", TextArea).text,
            self.query_one("#signature-context-policy", TextArea).text,
            tuple(self.query_one("#signature-tools-list", SelectionList).selected),
        ]
        for index in range(self.INPUT_COUNT):
            values.extend((
                self._row(index).styles.display,
                self.query_one(f"#signature-alias-{index}", Input).value,
                self.query_one(f"#signature-source-{index}", Input).value,
                self.query_one(f"#signature-schema-{index}", Input).value,
            ))
        return tuple(values)

    def _row(self, index: int) -> Horizontal:
        return self.query_one(f"#signature-input-row-{index}", Horizontal)

    def _set_input(self, widget_id: str, value: str) -> None:
        widget = self.query_one(f"#{widget_id}", Input)
        widget.value = value

    def _set_text(self, widget_id: str, value: str) -> None:
        widget = self.query_one(f"#{widget_id}", TextArea)
        widget.load_text(value)

    def _json_value(self, widget_id: str, label: str) -> Any:
        try:
            return json.loads(self.query_one(f"#{widget_id}", TextArea).text or "null")
        except json.JSONDecodeError as error:
            raise ValueError(f"{label} JSON: {error.msg}") from error

    def _json_object(self, widget_id: str, label: str) -> dict[str, Any]:
        value = self._json_value(widget_id, label)
        if not isinstance(value, dict):
            raise ValueError(f"{label} must be a JSON object")
        return value

    def _sync_raw_inputs(self, inputs: dict[str, SignatureInput]) -> None:
        value = {
            alias: {"source": item.source, "schema": item.schema}
            for alias, item in inputs.items()
        }
        self._set_text("signature-inputs-raw", json.dumps(value, sort_keys=True, indent=2))

    def _update_instruction_count(self) -> None:
        if self.is_mounted:
            length = len(self.query_one("#signature-instruction", TextArea).text)
            self.query_one("#signature-char-count", Static).update(f"{length} characters")

    def _update_preview(self) -> None:
        if not self.is_mounted:
            return
        try:
            patch = self.value(self._kind)
            input_names = tuple(patch["inputs"])
            sources = {name: item.source for name, item in patch["inputs"].items()}
            values = {name: f"<{source}>" for name, source in sources.items()}
            preview = render_signature_prompt(
                patch["instruction"], input_names, (patch["output"].name,), patch["examples"],
                values=values,
                react=self._kind == "react",
            )
            if self._kind == "react":
                preview += "\nTools exposed: " + (", ".join(patch["tools"]) or "none")
            self.query_one("#signature-preview", Static).update(preview)
            self.query_one("#signature-editor-error", Static).update("")
        except (ValueError, json.JSONDecodeError) as error:
            self.query_one("#signature-editor-error", Static).update(str(error))


__all__ = ["SignatureChanged", "SignatureEditor"]