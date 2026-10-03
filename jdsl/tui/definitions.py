"""Tool-capability and reusable-signature definitions screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Select, Static, TabbedContent, TabPane

from jdsl.ir.schema import BehaviorIR
from jdsl.package import ToolContract, ToolEffects


class DefinitionsScreen(ModalScreen[list[ToolContract] | None]):
    def __init__(self, contracts: list[ToolContract], ir: BehaviorIR) -> None:
        super().__init__()
        self.contracts = {contract.logical_id: contract for contract in contracts}
        self.ir = ir
        self.selected_id: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="definitions-dialog"):
            yield Static("Definitions", classes="dialog-title")
            with TabbedContent(id="definitions-tabs"):
                with TabPane("Tools", id="definitions-tools-pane"):
                    yield DataTable(id="definitions-tools-table", zebra_stripes=True)
                    with Horizontal(classes="definition-fields"):
                        yield Input(placeholder="Logical capability ID", id="definition-id")
                        yield Input(placeholder="Description", id="definition-description")
                    with Horizontal(classes="definition-fields"):
                        yield Input(placeholder="Argument names, comma separated", id="definition-arguments")
                        yield Select(
                            [("Read-only", "read-only"), ("Write", "write"), ("Destructive", "destructive")],
                            value="read-only",
                            id="definition-effect",
                        )
                    with Horizontal(classes="actions"):
                        yield Button("Add / update", id="definition-save", variant="primary")
                        yield Button("Remove", id="definition-remove")
                with TabPane("Signatures", id="definitions-signatures-pane"):
                    yield DataTable(id="definitions-signatures-table", zebra_stripes=True)
                    yield Static("Edit signatures from a predict/react node's inspector.", classes="field-label")
            with Horizontal(classes="actions"):
                yield Button("Done", id="definitions-done", variant="primary")
                yield Button("Cancel", id="definitions-cancel")

    def on_mount(self) -> None:
        tools = self.query_one("#definitions-tools-table", DataTable)
        tools.add_columns("Capability", "Effect", "Arguments", "Required")
        self._fill_tool_table()
        signatures = self.query_one("#definitions-signatures-table", DataTable)
        signatures.add_columns("Signature", "Kind", "Nodes", "Inputs", "Unused")
        usage: dict[str, int] = {}
        for node in self.ir.walk():
            signature_id = getattr(node, "signature", None)
            if signature_id:
                usage[signature_id] = usage.get(signature_id, 0) + 1
        for signature_id, signature in sorted(self.ir.signatures.items()):
            count = usage.get(signature_id, 0)
            signatures.add_row(
                signature_id,
                signature.kind,
                str(count),
                ", ".join(signature.inputs),
                "yes" if count == 0 else "",
                key=signature_id,
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "definitions-tools-table" and event.row_key:
            self.selected_id = str(event.row_key.value)
            contract = self.contracts.get(self.selected_id)
            if contract is not None:
                self.query_one("#definition-id", Input).value = contract.logical_id
                self.query_one("#definition-description", Input).value = contract.description
                properties = contract.input_schema.get("properties", {})
                self.query_one("#definition-arguments", Input).value = ", ".join(properties)
                effect = (
                    "destructive" if contract.effects.destructive
                    else "read-only" if contract.effects.read_only
                    else "write"
                )
                self.query_one("#definition-effect", Select).value = effect

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "definition-save":
            self._save_contract()
        elif button_id == "definition-remove":
            logical_id = self.query_one("#definition-id", Input).value.strip() or self.selected_id
            if logical_id:
                self.contracts.pop(logical_id, None)
                self.selected_id = None
                self._fill_tool_table()
        elif button_id == "definitions-done":
            self.dismiss(list(self.contracts.values()))
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save_contract(self) -> None:
        logical_id = self.query_one("#definition-id", Input).value.strip()
        if not logical_id:
            self.notify("Capability ID is required.", severity="warning")
            return
        names = [
            name.strip()
            for name in self.query_one("#definition-arguments", Input).value.split(",")
            if name.strip()
        ]
        effect = str(self.query_one("#definition-effect", Select).value)
        self.contracts[logical_id] = ToolContract(
            logical_id=logical_id,
            description=self.query_one("#definition-description", Input).value.strip(),
            input_schema={
                "type": "object",
                "properties": {name: {"type": "string"} for name in names},
                "required": names,
            },
            effects=ToolEffects(
                read_only=effect == "read-only",
                destructive=effect == "destructive",
                idempotent=effect != "destructive",
            ),
        )
        self.selected_id = logical_id
        self._fill_tool_table()

    def _fill_tool_table(self) -> None:
        table = self.query_one("#definitions-tools-table", DataTable)
        table.clear(columns=False)
        required = {
            node.tool for node in self.ir.walk()
            if getattr(node, "type", None) == "action" and getattr(node, "tool", None)
        }
        required.update(
            tool for signature in self.ir.signatures.values()
            if signature.kind == "react" for tool in signature.tools
        )
        for logical_id, contract in sorted(self.contracts.items()):
            effect = (
                "destructive" if contract.effects.destructive
                else "read-only" if contract.effects.read_only
                else "write"
            )
            table.add_row(
                logical_id,
                effect,
                ", ".join(contract.input_schema.get("properties", {})),
                "yes" if logical_id in required else "no",
                key=logical_id,
            )


__all__ = ["DefinitionsScreen"]
