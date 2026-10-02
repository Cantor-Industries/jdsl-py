"""Skill authoring workbench used by the Textual TUI."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from threading import Event
import time
from collections.abc import Callable
from copy import deepcopy
from functools import partial, wraps
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Collapsible, Input, Label, SelectionList, Static, Switch, TextArea, Tree
from textual.widgets.tree import TreeNode
from textual.worker import Worker, WorkerState

from jdsl.ir import (
    BehaviorIR,
    IRAction,
    IRGuard,
    IRNode,
    IRPredict,
    IRReact,
    IRRepeat,
    IRSelector,
    IRSequence,
    validate_ir,
)
from jdsl.ir.schema import IRComposite, Signature, SignatureInput, SignatureOutput
from jdsl.package import (
    BehaviorPackage,
    Manifest,
    ToolContract,
    export_jdsl,
    load_package,
    load_package_object,
    package_digest,
)
from jdsl.trace.sink import ListTraceSink
from jdsl.trace.redaction import Redactor
from jdsl.tui.dialogs import ConfirmDiscardScreen, TrustToolsScreen
from jdsl.tui.definitions import DefinitionsScreen
from jdsl.tui.editors import ActionArgumentsEditor, ArgumentsChanged, GuardChanged, GuardExpressionEditor
from jdsl.tui.run_panel import RunPanel, RunTraceUpdate
from jdsl.tui.run_inputs import RunInputsEditor
from jdsl.tui.screens import HelpScreen, NewTemplateScreen, OpenPackageScreen, SavePackageScreen, TourScreen
from jdsl.tui.settings import recovery_path
from jdsl.tui.signature_editor import SignatureChanged, SignatureEditor
from jdsl_harness.metrics import package_metrics


class _StreamingTraceSink(ListTraceSink):
    def __init__(self, on_event: Callable, cancel_event: Event) -> None:
        super().__init__()
        self.on_event = on_event
        self.cancel_event = cancel_event

    def emit(self, event):
        if self.cancel_event.is_set():
            raise _RunCancelled
        event = super().emit(event)
        try:
            self.on_event(event)
        except Exception:  # noqa: BLE001 - observation must not fail the runtime
            pass
        return event


def _dry_run_tool(logical_id: str, tool: Callable) -> Callable:
    @wraps(tool)
    def record_intent(*_args, **_kwargs):
        return {"dry_run": True, "tool": logical_id}

    return record_intent


class _RunCancelled(Exception):
    """Cooperative cancellation requested between runtime operations."""


def _cancellable_tool(tool: Callable, cancel_event: Event) -> Callable:
    @wraps(tool)
    def invoke(*args, **kwargs):
        if cancel_event.is_set():
            raise _RunCancelled
        return tool(*args, **kwargs)

    return invoke


def _referenced_paths(value: Any):
    if isinstance(value, dict):
        if set(value) == {"ref"}:
            yield str(value["ref"])
            return
        if set(value) == {"const"}:
            return
        if set(value) == {"exists"} and isinstance(value["exists"], str):
            yield value["exists"]
            return
        for child in value.values():
            yield from _referenced_paths(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _referenced_paths(child)


def _dynamic_indices(path: str) -> list[str]:
    return re.findall(r"\[\$([^\]]+)\]", path)


class SkillWorkbench(Vertical):
    """IR-backed tree editor for authored and compiled JDSL skills."""

    def __init__(self, *, status: Callable[[str], None] | None = None) -> None:
        super().__init__(id="skill-workspace")
        self.status = status or (lambda _message: None)
        self.skill_ir = BehaviorIR(root=IRSequence(type="sequence", id="root", children_=[]))
        self.selected_node: IRNode = self.skill_ir.root
        self._tree_node: TreeNode[IRNode] | None = None
        self.runtime_status: dict[str, str] = {}
        self.dirty = False
        self.valid: bool | None = None
        self.file_path: Path | None = None
        self._undo_stack: list[BehaviorIR] = []
        self._redo_stack: list[BehaviorIR] = []
        self._loading_properties = False
        self._apply_timer = None
        self._programmatic_change_counts: dict[str, int] = {}
        self._clipboard: IRNode | None = None
        self.tool_contracts: dict[str, ToolContract] = {}

    def compose(self) -> ComposeResult:
        yield Static("new-skill.jdsl  ·  ? unvalidated", id="skill-state")
        yield Static("Select a node, configure it, then validate or run.", id="skill-status")
        with Horizontal(id="recovery-banner"):
            yield Static("An autosaved recovery draft is available.")
            yield Button("Recover", id="recover-draft", variant="primary")
            yield Button("Discard draft", id="discard-draft")
        with Horizontal(id="skill-tree-panel"):
            with Vertical():
                yield Static("SKILL TREE", classes="panel-title")
                yield Input(placeholder="Find node ID or type (Ctrl+F)", id="tree-search")
                yield Tree("root", id="skill-tree")
                with Vertical(id="empty-state"):
                    yield Static("A new skill starts here.", classes="dialog-title")
                    with Horizontal(classes="actions"):
                        yield Button("New from template", id="empty-new", variant="primary")
                        yield Button("Open package", id="empty-open")
                        yield Button("Tour", id="empty-tour")
                with Horizontal(id="skill-actions"):
                    with Horizontal(classes="action-row"):
                        for node_type in ("sequence", "selector", "action", "guard"):
                            yield Button(f"+ {node_type}", id=f"add-{node_type}")
                    with Horizontal(classes="action-row"):
                        for node_type in ("predict", "react", "repeat"):
                            yield Button(f"+ {node_type}", id=f"add-{node_type}")
                        yield Button("Remove", id="remove-node")
                    with Horizontal(id="editing-actions", classes="action-row"):
                        yield Button("Up", id="move-up")
                        yield Button("Down", id="move-down")
                        yield Button("Indent", id="indent-node")
                        yield Button("Outdent", id="outdent-node")
                        yield Button("Duplicate", id="duplicate-node")
                        yield Button("Copy", id="copy-node")
                        yield Button("Paste", id="paste-node")
                        yield Button("Definitions", id="definitions")
            with Vertical(id="skill-properties-panel"):
                yield Static("NODE PROPERTIES", classes="panel-title")
                yield Static("Not validated yet.", id="skill-problems")
                with VerticalScroll(id="skill-properties-scroll"):
                    with Vertical(id="skill-properties"):
                        yield Label("Select a node")
                        yield Input(placeholder="Node id", id="node-id")
                        with Horizontal(id="action-fields", classes="field-row"):
                            yield Input(placeholder="Tool capability", id="node-tool")
                            yield Input(placeholder="Store result as", id="node-store")
                        with Horizontal(id="repeat-fields", classes="field-row"):
                            yield Input(placeholder="Repeat max", id="repeat-max")
                        yield ActionArgumentsEditor(id="action-arguments")
                        yield GuardExpressionEditor(id="guard-fields")
                        with Horizontal(id="signature-fields", classes="field-row"):
                            yield Input(placeholder="Signature id", id="node-signature")
                            yield Input(placeholder="Model / provider", id="node-model")
                        yield SignatureEditor(id="signature-editor")
                    with Collapsible(title="Package", collapsed=True, id="package-settings"):
                        with Horizontal(classes="field-row"):
                            yield Input(placeholder="Package name", value="new-skill", id="skill-name")
                            yield Input(placeholder="Output path", value="new-skill.jdsl", id="skill-out")
                        yield Input(placeholder="Package path to open", id="open-path")
                        yield SelectionList(id="recent-files")
                        yield Button("Open selected recent", id="open-recent")
                    with Collapsible(title="Run", collapsed=True, id="run-settings"):
                        yield Static("Trusted tools: none", id="trusted-tools-state")
                        with Horizontal(classes="field-row"):
                            yield Input(placeholder="Tools module path (trusted Python code)", id="run-tools")
                            yield Input(placeholder="Run model id", id="run-model")
                        with Horizontal(classes="field-row"):
                            yield Static("Dry run", classes="field-label")
                            yield Switch(id="dry-run")
                        yield RunInputsEditor(id="run-input-editor")
                with Horizontal(classes="actions"):
                    yield Button("Apply", id="apply-properties", variant="primary")
                    yield Button("Validate", id="validate-skill")
                    yield Button("Save", id="save-skill", variant="success")
                    yield Button("Open", id="open-skill")
                    yield Button("New", id="new-skill")
                    yield Button("Run", id="run-skill", variant="primary")
                    yield Button("Stop", id="stop-run", disabled=True)
                yield RunPanel(id="run-panel")

    def on_mount(self) -> None:
        self.query_one("#run-panel", RunPanel).styles.display = "none"
        self.query_one("#tree-search", Input).styles.display = "none"
        self.query_one("#recovery-banner").styles.display = "none"
        self.rebuild_tree()
        self._refresh_run_inputs()
        self._refresh_recent_files()
        self._update_empty_state()
        if recovery_path().is_file():
            self.query_one("#recovery-banner").styles.display = "block"
        self._update_state()
        self.query_one("#skill-tree", Tree).focus()

    @staticmethod
    def node_label(node: IRNode) -> str:
        detail = ""
        if isinstance(node, IRAction):
            detail = f" {node.tool or '(tool)'}"
        elif isinstance(node, (IRPredict, IRReact)):
            detail = f" {node.signature or '(signature)'}"
        return f"{node.type}{detail}" + (f"  #{node.id}" if node.id else "")

    def display_label(self, node: IRNode) -> Text:
        status = self.runtime_status.get(node.id or "")
        unicode_glyphs = {
            "sequence": "→", "selector": "?", "action": "▶", "guard": "◆",
            "predict": "✦", "react": "↻", "repeat": "⟲",
        }
        ascii_glyphs = {
            "sequence": ">", "selector": "?", "action": "*", "guard": "!",
            "predict": "~", "react": "<>", "repeat": "+",
        }
        glyphs = ascii_glyphs if self.app.settings.ascii_glyphs else unicode_glyphs
        glyph = glyphs.get(node.type, ".")
        marks = {"success": " ok", "failure": " x", "running": " ..."} if self.app.settings.ascii_glyphs else {
            "success": " ✔", "failure": " ✖", "running": " …"
        }
        mark = marks.get(status, "")
        role = {
            "sequence": "blue", "selector": "blue", "repeat": "blue",
            "action": "green", "guard": "yellow", "predict": "magenta", "react": "magenta",
        }.get(node.type, "white")
        label = Text()
        label.append(f"{glyph} ", style=role)
        label.append(self.node_label(node), style=role)
        if mark:
            label.append(mark, style="red" if status == "failure" else "green")
        return label

    def rebuild_tree(self) -> None:
        selected = self.selected_node
        tree = self.query_one("#skill-tree", Tree)
        expanded = self._expanded_ids(tree.root)
        tree.clear()
        root = tree.root
        root.label = self.display_label(self.skill_ir.root)
        root.data = self.skill_ir.root
        self._add_children(root, self.skill_ir.root, expanded)
        root.expand()
        self.select_node(self._find_tree_node(root, selected) or root)
        self._update_empty_state()

    def _expanded_ids(self, tree_node: TreeNode[IRNode]) -> set[str]:
        expanded = {tree_node.data.id} if tree_node.data and tree_node.data.id and tree_node.is_expanded else set()
        for child in tree_node.children:
            expanded.update(self._expanded_ids(child))
        return expanded

    def _add_children(self, parent: TreeNode[IRNode], node: IRNode, expanded: set[str] | None = None) -> None:
        expanded = expanded or set()
        for child in node.children():
            child_node = parent.add(self.display_label(child), data=child)
            self._add_children(child_node, child, expanded)
            if child.id and child.id in expanded:
                child_node.expand()

    def _find_tree_node(self, parent: TreeNode[IRNode], target: IRNode) -> TreeNode[IRNode] | None:
        if parent.data is target:
            return parent
        for child in parent.children:
            found = self._find_tree_node(child, target)
            if found is not None:
                return found
        return None

    def on_tree_node_selected(self, event: Tree.NodeSelected[IRNode]) -> None:
        self.select_node(event.node)

    def select_node(self, tree_node: TreeNode[IRNode]) -> None:
        if tree_node.data is None:
            return
        self._tree_node = tree_node
        self.selected_node = tree_node.data
        self.populate_properties(tree_node.data)

    def _input(self, field: str) -> str:
        widget = self.query_one(f"#{field}")
        value = widget.text if isinstance(widget, TextArea) else widget.value
        return value.strip()

    def _csv(self, field: str) -> list[str]:
        return [value.strip() for value in self._input(field).split(",") if value.strip()]

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tree-search":
            if event.value.strip():
                self.jump_to_node(event.value)
            return
        self._queue_property_apply(event.input.id, event.value)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._queue_property_apply(event.text_area.id, event.text_area.text)

    def _queue_property_apply(self, field_id: str | None, value: str = "") -> None:
        property_fields = {
            "node-id", "node-tool", "node-store", "node-arguments", "node-expression",
            "action-arguments", "guard-fields",
            "node-signature", "node-model", "signature-inputs", "signature-output",
            "signature-instructions", "signature-tools", "signature-editor", "repeat-max",
        }
        if self._loading_properties or field_id not in property_fields:
            return
        if self._programmatic_change_counts.get(field_id, 0):
            self._programmatic_change_counts[field_id] -= 1
            if self._programmatic_change_counts[field_id] == 0:
                self._programmatic_change_counts.pop(field_id)
            return
        if self._apply_timer is not None:
            self._apply_timer.stop()
        self._apply_timer = self.set_timer(0.35, self._apply_pending_properties)

    def on_arguments_changed(self, _event: ArgumentsChanged) -> None:
        self._queue_property_apply("action-arguments")

    def on_guard_changed(self, _event: GuardChanged) -> None:
        self._queue_property_apply("guard-fields")

    def on_signature_changed(self, _event: SignatureChanged) -> None:
        self._queue_property_apply("signature-editor")

    def _apply_pending_properties(self) -> None:
        self._apply_timer = None
        self.apply_properties()

    def populate_properties(self, node: IRNode) -> None:
        if self._apply_timer is not None:
            self._apply_timer.stop()
            self._apply_timer = None
        signature = self.skill_ir.signatures.get(node.signature) if isinstance(node, (IRPredict, IRReact)) else None
        values = {
            "node-id": node.id or "",
            "node-tool": node.tool if isinstance(node, IRAction) else "",
            "node-store": (node.store or "") if isinstance(node, IRAction) else "",
            "node-signature": node.signature if isinstance(node, (IRPredict, IRReact)) else "",
            "node-model": signature.context_policy.get("model", "") if signature else "",
            "repeat-max": str(node.max) if isinstance(node, IRRepeat) else "",
        }
        self._loading_properties = True
        try:
            for field, value in values.items():
                widget = self.query_one(f"#{field}")
                old_value = widget.text if isinstance(widget, TextArea) else widget.value
                if old_value != value:
                    self._programmatic_change_counts[field] = self._programmatic_change_counts.get(field, 0) + 1
                if isinstance(widget, TextArea):
                    widget.load_text(value)
                else:
                    widget.value = value
        finally:
            self._loading_properties = False
        self.query_one("#action-arguments", ActionArgumentsEditor).load(
            node.arguments if isinstance(node, IRAction) else {}
        )
        self.query_one("#guard-fields", GuardExpressionEditor).load(
            node.expression if isinstance(node, IRGuard) else {}
        )
        self.query_one("#signature-editor", SignatureEditor).load(
            signature,
            sorted(self._capabilities()),
            "react" if isinstance(node, IRReact) else "predict",
        )
        visible_fields = {
            "action-fields": isinstance(node, IRAction),
            "action-arguments": isinstance(node, IRAction),
            "guard-fields": isinstance(node, IRGuard),
            "signature-fields": isinstance(node, (IRPredict, IRReact)),
            "signature-editor": isinstance(node, (IRPredict, IRReact)),
            "repeat-fields": isinstance(node, IRRepeat),
        }
        for widget_id, visible in visible_fields.items():
            self.query_one(f"#{widget_id}").styles.display = "block" if visible else "none"
        self.query_one("#skill-properties Label", Label).update(f"{node.type.upper()}  ·  {self.node_label(node)}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("add-"):
            self.add_node(button_id.removeprefix("add-"))
        elif button_id == "remove-node":
            self.remove_selected_node()
        elif button_id == "apply-properties":
            self.apply_properties()
        elif button_id == "validate-skill":
            self.validate_skill()
        elif button_id == "save-skill":
            self.request_save()
        elif button_id == "run-skill":
            self.run_skill()
        elif button_id == "open-skill":
            self.open_skill()
        elif button_id == "new-skill":
            self.request_new_skill()
        elif button_id == "stop-run":
            self.cancel_run()
        elif button_id == "move-up":
            self.move_selected(-1)
        elif button_id == "move-down":
            self.move_selected(1)
        elif button_id == "indent-node":
            self.indent_selected()
        elif button_id == "outdent-node":
            self.outdent_selected()
        elif button_id == "duplicate-node":
            self.duplicate_selected_node()
        elif button_id == "copy-node":
            self.copy_selected_node()
        elif button_id == "paste-node":
            self.paste_node()
        elif button_id == "open-recent":
            self.open_recent()
        elif button_id == "empty-new":
            self.request_new_skill()
        elif button_id == "empty-open":
            self.open_skill()
        elif button_id == "empty-tour":
            self.show_tour()
        elif button_id == "recover-draft":
            self.recover_draft()
        elif button_id == "discard-draft":
            self.discard_recovery_draft()
        elif button_id == "help":
            self.show_help()
        elif button_id == "definitions":
            self.open_definitions()

    def add_node(self, node_type: str) -> None:
        parent = self.selected_node if isinstance(self.selected_node, (IRComposite, IRRepeat)) else self.skill_ir.root
        if isinstance(parent, IRRepeat) and parent.child is not None:
            parent = self.skill_ir.root
        node_id = self._new_node_id(node_type)
        nodes: dict[str, IRNode] = {
            "sequence": IRSequence(type="sequence", id=node_id, children_=[]),
            "selector": IRSelector(type="selector", id=node_id, children_=[]),
            "action": IRAction(type="action", id=node_id, tool=""),
            "guard": IRGuard(type="guard", id=node_id, expression={}),
            "predict": IRPredict(type="predict", id=node_id, signature=""),
            "react": IRReact(type="react", id=node_id, signature=""),
            "repeat": IRRepeat(type="repeat", id=node_id, child=None, max=3),
        }
        new_node = nodes[node_type]
        self._record_history()
        if isinstance(parent, IRRepeat) and parent.child is None:
            parent.child = new_node
        else:
            parent.children_.append(new_node)
        self._mark_dirty()
        self.rebuild_tree()
        self.write_status(f"Added {node_type} under {parent.type}. Configure it in the properties panel.")

    def apply_properties(self) -> None:
        node = self.selected_node
        action_arguments = None
        guard_expression = None
        repeat_max = None
        signature_patch = None
        if isinstance(node, IRAction):
            try:
                action_arguments = self.query_one("#action-arguments", ActionArgumentsEditor).value()
            except (ValueError, json.JSONDecodeError) as error:
                self.write_status(f"Action arguments are invalid: {error}")
                return
        if isinstance(node, IRGuard):
            try:
                guard_expression = self.query_one("#guard-fields", GuardExpressionEditor).value()
            except (ValueError, json.JSONDecodeError) as error:
                self.write_status(f"Guard expression is invalid: {error}")
                return
        if isinstance(node, IRRepeat):
            try:
                repeat_max = int(self._input("repeat-max") or "3")
            except ValueError:
                self.write_status("Repeat max must be an integer.")
                return
        if isinstance(node, (IRPredict, IRReact)):
            try:
                signature_patch = self.query_one("#signature-editor", SignatureEditor).value(
                    "react" if isinstance(node, IRReact) else "predict"
                )
            except ValueError as error:
                self.write_status(f"Signature is invalid: {error}")
                return
        signature_id = None
        if isinstance(node, (IRPredict, IRReact)):
            signature_id = self._input("node-signature") or f"sig_{self._input('node-id') or node.type}"
            if signature_id != node.signature and signature_id in self.skill_ir.signatures:
                self.write_status(f"Signature id {signature_id!r} is already in use.")
                return
        self._record_history()
        node.id = self._input("node-id") or None
        if isinstance(node, IRAction):
            node.tool = self._input("node-tool")
            node.store = self._input("node-store") or None
            node.arguments = action_arguments
        if isinstance(node, IRGuard):
            node.expression = guard_expression
        if isinstance(node, (IRPredict, IRReact)):
            previous_id = node.signature
            node.signature = signature_id
            model = self._input("node-model")
            signature = self.skill_ir.signatures.get(signature_id)
            if signature is None:
                signature = self.skill_ir.signatures.get(previous_id)
            if signature is None:
                signature = Signature(id=signature_id)
            if previous_id != signature_id:
                self.skill_ir.signatures.pop(previous_id, None)
            signature.id = signature_id
            signature.kind = "react" if isinstance(node, IRReact) else "predict"
            signature.inputs = signature_patch["inputs"]
            signature.output = signature_patch["output"]
            signature.instruction = signature_patch["instruction"]
            signature.examples = signature_patch["examples"]
            signature.validator = signature_patch["validator"]
            signature.context_policy = signature_patch["context_policy"]
            if isinstance(node, IRReact):
                signature.tools = signature_patch["tools"]
            if model:
                signature.context_policy["model"] = model
            else:
                signature.context_policy.pop("model", None)
            self.skill_ir.signatures[signature_id] = signature
        if isinstance(node, IRRepeat):
            node.max = repeat_max
        self._mark_dirty()
        self.rebuild_tree()
        self.write_status(f"Applied properties to {node.type}.")

    def remove_selected_node(self) -> None:
        if self.selected_node is self.skill_ir.root:
            self.write_status("The root node cannot be removed.")
            return
        self._record_history()
        if self._remove_from(self.skill_ir.root, self.selected_node):
            self.rebuild_tree()
            self.write_status("Removed selected node.")

    def move_selected(self, offset: int) -> None:
        parent = self._parent_of(self.skill_ir.root, self.selected_node)
        if not isinstance(parent, IRComposite):
            self.write_status("Only composite children can move between siblings.")
            return
        siblings = parent.children_
        current = siblings.index(self.selected_node)
        destination = current + offset
        if not 0 <= destination < len(siblings):
            return
        self._record_history()
        siblings[current], siblings[destination] = siblings[destination], siblings[current]
        self._mark_dirty()
        self.rebuild_tree()

    def indent_selected(self) -> None:
        parent = self._parent_of(self.skill_ir.root, self.selected_node)
        if not isinstance(parent, IRComposite):
            self.write_status("Only composite children can be indented.")
            return
        siblings = parent.children_
        current = siblings.index(self.selected_node)
        if current == 0:
            self.write_status("There is no previous sibling to indent under.")
            return
        previous = siblings[current - 1]
        if not isinstance(previous, (IRComposite, IRRepeat)):
            self.write_status("Indent requires a previous sequence, selector, or empty repeat.")
            return
        if isinstance(previous, IRRepeat) and previous.child is not None:
            self.write_status("That repeat already has a child.")
            return
        self._record_history()
        siblings.pop(current)
        self._attach_child(previous, self.selected_node)
        self._mark_dirty()
        self.rebuild_tree()

    def outdent_selected(self) -> None:
        parent = self._parent_of(self.skill_ir.root, self.selected_node)
        grandparent = self._parent_of(self.skill_ir.root, parent) if parent else None
        if parent is None or parent is self.skill_ir.root or not isinstance(grandparent, IRComposite):
            self.write_status("The selected node cannot be outdented further.")
            return
        siblings = grandparent.children_
        parent_index = siblings.index(parent)
        self._record_history()
        if not self._remove_from(parent, self.selected_node):
            return
        siblings.insert(parent_index + 1, self.selected_node)
        self._mark_dirty()
        self.rebuild_tree()

    def copy_selected_node(self) -> None:
        if self.selected_node is self.skill_ir.root:
            self.write_status("The root cannot be copied as a subtree.")
            return
        self._clipboard = deepcopy(self.selected_node)
        self.write_status("Copied subtree.")

    def duplicate_selected_node(self) -> None:
        if self.selected_node is self.skill_ir.root:
            self.write_status("The root cannot be duplicated as a sibling.")
            return
        duplicate = deepcopy(self.selected_node)
        self._insert_sibling(duplicate)

    def paste_node(self) -> None:
        if self._clipboard is None:
            self.write_status("Clipboard is empty.")
            return
        self._insert_sibling(deepcopy(self._clipboard))

    def _insert_sibling(self, node: IRNode) -> None:
        parent = self._parent_of(self.skill_ir.root, self.selected_node)
        if isinstance(parent, IRComposite):
            siblings = parent.children_
            index = siblings.index(self.selected_node)
            self._record_history()
            self._assign_fresh_ids(node)
            siblings.insert(index + 1, node)
        elif isinstance(parent, IRRepeat) and parent.child is None:
            self._record_history()
            self._assign_fresh_ids(node)
            parent.child = node
        else:
            self.write_status("The selected node has no available sibling slot.")
            return
        self.selected_node = node
        self._mark_dirty()
        self.rebuild_tree()

    def _assign_fresh_ids(self, node: IRNode) -> None:
        reserved: set[str] = set()
        stack = [node]
        while stack:
            current = stack.pop()
            current.id = self._fresh_node_id(current.type, reserved)
            stack.extend(reversed(current.children()))

    def _fresh_node_id(self, node_type: str, reserved: set[str]) -> str:
        existing = {item.id for item in self.skill_ir.walk() if item.id} | reserved
        suffix = 0
        while f"{node_type}_{suffix}" in existing:
            suffix += 1
        result = f"{node_type}_{suffix}"
        reserved.add(result)
        return result

    def _parent_of(self, parent: IRNode, target: IRNode) -> IRNode | None:
        for child in parent.children():
            if child is target:
                return parent
            found = self._parent_of(child, target)
            if found is not None:
                return found
        return None

    def _attach_child(self, parent: IRNode, child: IRNode) -> bool:
        if isinstance(parent, IRComposite):
            parent.children_.append(child)
            return True
        if isinstance(parent, IRRepeat) and parent.child is None:
            parent.child = child
            return True
        return False

    def focus_search(self) -> None:
        search = self.query_one("#tree-search", Input)
        search.styles.display = "block"
        search.focus()

    def jump_to_node(self, query: str) -> bool:
        normalized = query.strip().casefold()
        if not normalized:
            return False
        node = next(
            (item for item in self.skill_ir.walk() if item.id and item.id.casefold() == normalized),
            None,
        )
        if node is None:
            node = next(
                (item for item in self.skill_ir.walk() if normalized in self.node_label(item).casefold()),
                None,
            )
        if node is None:
            return False
        tree = self.query_one("#skill-tree", Tree)
        found = self._find_tree_node(tree.root, node)
        if found:
            self._expand_path(tree.root, node)
            tree.select_node(found)
            self.select_node(found)
            return True
        return False

    def _expand_path(self, parent: TreeNode[IRNode], target: IRNode) -> bool:
        for child in parent.children:
            if child.data is target:
                parent.expand()
                return True
            if self._expand_path(child, target):
                child.expand()
                return True
        return False

    def toggle_dry_run(self) -> None:
        toggle = self.query_one("#dry-run", Switch)
        toggle.value = not toggle.value
        self.write_status(f"Dry run {'on' if toggle.value else 'off'}.")

    def _remove_from(self, parent: IRNode, target: IRNode) -> bool:
        if isinstance(parent, IRComposite) and target in parent.children_:
            parent.children_.remove(target)
            return True
        if isinstance(parent, IRRepeat):
            if parent.child is target:
                parent.child = None
                return True
            if parent.until is target:
                parent.until = None
                return True
        return any(self._remove_from(child, target) for child in parent.children())

    def _new_node_id(self, node_type: str) -> str:
        existing = {node.id for node in self.skill_ir.walk() if node.id}
        suffix = 0
        while f"{node_type}_{suffix}" in existing:
            suffix += 1
        return f"{node_type}_{suffix}"

    def _mark_dirty(self) -> None:
        self.dirty = True
        self.runtime_status.clear()
        self._refresh_validation()
        self._refresh_run_inputs()
        self._autosave_draft()
        self._update_state()

    def _record_history(self) -> None:
        from copy import deepcopy

        self._undo_stack.append(deepcopy(self.skill_ir))
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> None:
        if not self._undo_stack:
            self.write_status("Nothing to undo.")
            return
        from copy import deepcopy

        self._redo_stack.append(deepcopy(self.skill_ir))
        self.skill_ir = self._undo_stack.pop()
        self._restore_selection()
        self._mark_dirty()
        self.rebuild_tree()
        self.write_status("Undid the last edit.")

    def redo(self) -> None:
        if not self._redo_stack:
            self.write_status("Nothing to redo.")
            return
        from copy import deepcopy

        self._undo_stack.append(deepcopy(self.skill_ir))
        self.skill_ir = self._redo_stack.pop()
        self._restore_selection()
        self._mark_dirty()
        self.rebuild_tree()
        self.write_status("Redid the last edit.")

    def _restore_selection(self) -> None:
        selected_id = self.selected_node.id
        self.selected_node = next(
            (node for node in self.skill_ir.walk() if node.id == selected_id), self.skill_ir.root
        )

    def _update_state(self) -> None:
        if not self.is_mounted:
            return
        name = self._input("skill-out") if self.query("#skill-out") else "new-skill.jdsl"
        dirty = " ●" if self.dirty else ""
        validity = "✔ valid" if self.valid else "✖ invalid" if self.valid is False else "? unvalidated"
        metric = package_metrics(self.skill_ir)
        capabilities = sorted(self._capabilities())
        state = self.query_one("#skill-state", Static)
        state.update(
            f"{name or 'new-skill.jdsl'}{dirty}  ·  {validity}  ·  "
            f"RDB {metric.residual_decision_burden:.2f}  ·  {len(capabilities)} tools"
        )
        state.tooltip = "Required tools: " + (", ".join(capabilities) if capabilities else "none")

    def _capabilities(self) -> set[str]:
        caps = {node.tool for node in self.skill_ir.walk() if isinstance(node, IRAction) and node.tool}
        caps.update(
            tool for signature in self.skill_ir.signatures.values()
            if signature.kind == "react" for tool in signature.tools
        )
        return caps

    def validate_skill(self) -> bool:
        report = validate_ir(self.skill_ir, required_capabilities=self._capabilities())
        self._refresh_validation(report)
        if report.ok:
            self.write_status("Valid behavior tree. Ready to save.")
            return True
        self.write_status("Validation failed: " + "; ".join(report.problems))
        return False

    def _refresh_validation(self, report=None) -> None:
        if report is None:
            report = validate_ir(self.skill_ir, required_capabilities=self._capabilities())
        self.valid = report.ok
        if self.is_mounted:
            content = Text()
            if report.ok:
                content.append("No problems.", style="green")
            else:
                content.append(f"{len(report.problems)} problem(s)\n", style="red bold")
                for problem in report.problems:
                    content.append(f"! {problem}\n", style="red")
            self.query_one("#skill-problems", Static).update(content)
        self._update_state()

    def request_save(self) -> None:
        if not self.validate_skill():
            return
        name = self._input("skill-name") or "new-skill"
        output = self._input("skill-out") or f"{name}.jdsl"
        description = "Authored in the JDSL workbench."
        package = self._build_package(name, "0.1.0", description)
        summary = (
            f"Capabilities: {', '.join(sorted(self._capabilities())) or 'none'}\n"
            f"Current digest preview: {package_digest(package)[:32]}…\n"
            "Editing package metadata changes this preview."
        )
        self.app.push_screen(
            SavePackageScreen(
                name=name,
                version="0.1.0",
                description=description,
                output=output,
                summary=summary,
            ),
            self._save_dialog_result,
        )

    def _save_dialog_result(self, values: dict[str, str] | None) -> None:
        if values is not None:
            self.save_skill(**values)

    def _build_package(self, name: str, version: str, description: str) -> BehaviorPackage:
        capabilities = sorted(self._capabilities())
        contracts = [
            self.tool_contracts.get(capability, ToolContract(logical_id=capability))
            for capability in capabilities
        ]
        return BehaviorPackage(
            manifest=Manifest(
                name=name,
                version=version or "0.1.0",
                required_capabilities=capabilities,
                source={"authoring": "jdsl-tui"},
            ),
            ir=self.skill_ir,
            tools=contracts,
            readme=f"# {name}\n\n{description or 'Authored in the JDSL workbench.'}\n",
        )

    def save_skill(
        self,
        *,
        name: str | None = None,
        version: str = "0.1.0",
        description: str = "",
        output: str | None = None,
    ) -> None:
        if not self.validate_skill():
            return
        name = name or self._input("skill-name") or "new-skill"
        output = output or self._input("skill-out") or f"{name}.jdsl"
        package = self._build_package(name, version, description)
        self.write_status("Exporting and verifying package…")
        try:
            path = export_jdsl(package, Path(output))
            load_package(path)
        except Exception as error:  # noqa: BLE001 - filesystem/package failures are user input
            self.write_status(f"Save failed: {error}", severity="error")
            return
        self.query_one("#skill-name", Input).value = name
        self.query_one("#skill-out", Input).value = str(path)
        self.dirty = False
        self.file_path = path
        self._clear_recovery_file()
        self._remember_recent(path)
        self._update_state()
        self.write_status(f"Saved and verified {path} ({package_digest(package)[:24]}...).", notify=True)

    def run_skill(self) -> None:
        tools_value = self._input("run-tools")
        if not tools_value:
            self.write_status("Run requires a Python tools module defining TOOLS.")
            return
        try:
            tools_path = Path(tools_value).expanduser().resolve()
            digest = hashlib.sha256(tools_path.read_bytes()).hexdigest()
            if self.app.settings.trusted_tools.get(str(tools_path)) == digest:
                self._start_run(tools_path, digest)
                return
            self.app.push_screen(
                TrustToolsScreen(str(tools_path), digest),
                partial(self._trust_tools_result, tools_path=tools_path, digest=digest),
            )
        except (OSError, ValueError) as error:
            self.write_status(f"Run failed: {error}")

    def _trust_tools_result(self, approved: bool | None, *, tools_path: Path, digest: str) -> None:
        if not approved:
            self.write_status("Run cancelled; the tools module was not imported.")
            return
        try:
            current_digest = hashlib.sha256(tools_path.read_bytes()).hexdigest()
            if current_digest != digest:
                self.write_status("Tools module changed after confirmation; review it again before running.")
                return
            self.app.settings.trusted_tools[str(tools_path)] = digest
            self.app.settings.save()
        except OSError as error:
            self.write_status(f"Could not remember tools trust: {error}")
            return
        self.query_one("#trusted-tools-state", Static).update(f"Trusted tools: {tools_path}")
        self._start_run(tools_path, digest)

    def _start_run(self, tools_path: Path, tools_digest: str) -> None:
        try:
            inputs = self.query_one("#run-input-editor", RunInputsEditor).value()
        except ValueError as error:
            self.write_status(f"Run input error: {error}")
            return
        if not self.validate_skill():
            return
        self.query_one("#trusted-tools-state", Static).update(f"Trusted tools: {tools_path}")
        dry_run = self.query_one("#dry-run", Switch).value
        self._run_cancel_event = Event()
        self.runtime_status.clear()
        self._run_panel().begin(len(self.skill_ir.walk()), dry_run=dry_run)
        self.query_one("#stop-run", Button).disabled = False
        mode = "Dry run" if dry_run else "Running"
        self.write_status(f"{mode} with trusted tools: {tools_path}")
        self._run_worker = self.run_worker(
            partial(
                self._execute_run,
                tools_path,
                tools_digest,
                self._input("skill-name") or "new-skill",
                self._input("run-model"),
                deepcopy(self.skill_ir),
                sorted(self._capabilities()),
                inputs,
                dry_run,
                self._run_cancel_event,
            ),
            name="skill-run",
            group="skill-run",
            exclusive=True,
            thread=True,
            exit_on_error=False,
        )

    def _execute_run(
        self,
        tools_path: Path,
        tools_digest: str,
        package_name: str,
        model_id: str,
        skill_ir: BehaviorIR,
        capabilities: list[str],
        inputs: dict[str, Any],
        dry_run: bool,
        cancel_event: Event,
    ) -> dict:
        started = time.monotonic()
        try:
            if hashlib.sha256(tools_path.read_bytes()).hexdigest() != tools_digest:
                raise ValueError("tools module changed after trust confirmation")
            spec = importlib.util.spec_from_file_location("jdsl_tui_tools", tools_path)
            if spec is None or spec.loader is None:
                raise ValueError(f"cannot import {tools_path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            tools = getattr(module, "TOOLS", None)
            if not isinstance(tools, dict):
                raise ValueError("tools module must define a TOOLS dict")
            if dry_run:
                tools = {name: _dry_run_tool(str(name), tool) for name, tool in tools.items()}
            tools = {name: _cancellable_tool(tool, cancel_event) for name, tool in tools.items()}
            package = BehaviorPackage(
                manifest=Manifest(name=package_name, required_capabilities=capabilities),
                ir=skill_ir,
                tools=[ToolContract(logical_id=capability) for capability in capabilities],
            )
            root = package_to_root(package, tools, getattr(module, "PREDICATES", {}), model_id)
            sink = _StreamingTraceSink(self._forward_trace, cancel_event)
            ctx = root.run(trace_sink=sink, **inputs)
            statuses = {
                str(event.payload["node_id"]): str(event.payload["status"])
                for event in sink.events
                if event.kind == "node.exit" and "node_id" in event.payload and "status" in event.payload
            }
            tool_calls = sum(event.kind == "tool.call.started" for event in sink.events)
            model_calls = sum(event.kind == "model.requested" for event in sink.events)
            return {
                "statuses": statuses,
                "elapsed": time.monotonic() - started,
                "tool_calls": tool_calls,
                "model_calls": model_calls,
                "dry_run": dry_run,
                "blackboard": Redactor().redact(dict(ctx.blackboard)),
            }
        except _RunCancelled:
            return {"cancelled": True, "elapsed": time.monotonic() - started}
        except Exception as error:  # noqa: BLE001 - return user-facing worker failure
            return {"error": str(error), "elapsed": time.monotonic() - started}

    def _forward_trace(self, event) -> None:
        payload = event.payload
        tool = payload.get("tool")
        tool_name = tool.get("host_name") if isinstance(tool, dict) else None
        update = RunTraceUpdate(event.kind, payload.get("node_id"), payload.get("status"), tool_name)
        self.app.call_from_thread(self.post_message, update)

    def on_run_trace_update(self, event: RunTraceUpdate) -> None:
        if event.kind == "node.enter" and event.node_id:
            self.runtime_status[event.node_id] = "running"
            self.rebuild_tree()
        elif event.kind == "node.exit" and event.node_id and event.status:
            self.runtime_status[event.node_id] = event.status
            self.rebuild_tree()
        self._run_panel().add_trace(event)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name != "skill-run":
            return
        if event.state is WorkerState.CANCELLED:
            self.query_one("#stop-run", Button).disabled = True
            self.write_status("Run cancelled.")
            self._run_panel().finish("Run cancelled.")
        elif event.state is WorkerState.SUCCESS:
            self.query_one("#stop-run", Button).disabled = True
            result = event.worker.result
            if result.get("cancelled"):
                self.write_status("Run cancelled.")
                self._run_panel().finish("Run cancelled.")
            elif result.get("error"):
                self.write_status(f"Run failed: {result['error']}")
                self._run_panel().finish(f"Run failed: {result['error']}")
            else:
                self.runtime_status = result["statuses"]
                self.rebuild_tree()
                summary = (
                    f"{'Dry run' if result['dry_run'] else 'Run complete'} in {result['elapsed']:.2f}s · "
                    f"{result['tool_calls']} tool calls · {result['model_calls']} model calls"
                )
                self.write_status(summary)
                self._run_panel().finish(summary)
                self._run_panel().show_blackboard(result["blackboard"])
        elif event.state is WorkerState.ERROR:
            self.query_one("#stop-run", Button).disabled = True
            message = str(event.worker.error or "unknown worker error")
            self.write_status(f"Run failed: {message}")
            self._run_panel().finish(f"Run failed: {message}")

    def cancel_run(self) -> None:
        worker = getattr(self, "_run_worker", None)
        if worker is not None and worker.state in {WorkerState.PENDING, WorkerState.RUNNING}:
            self._run_cancel_event.set()
            self.write_status("Stopping run…")

    def _run_panel(self) -> RunPanel:
        return self.query_one("#run-panel", RunPanel)

    def _refresh_run_inputs(self) -> None:
        if not self.is_mounted:
            return
        generated: set[str] = set()
        required: set[str] = set()
        for node in self.skill_ir.walk():
            references: list[str] = []
            if isinstance(node, IRAction):
                references.extend(_referenced_paths(node.arguments))
            elif isinstance(node, IRGuard):
                references.extend(_referenced_paths(node.expression))
            elif isinstance(node, (IRPredict, IRReact)):
                signature = self.skill_ir.signatures.get(node.signature)
                if signature:
                    references.extend(item.source.removeprefix("blackboard.") for item in signature.inputs.values())
            for reference in references:
                root = reference.split(".", 1)[0].split("[", 1)[0]
                if reference not in generated and root not in generated:
                    required.add(reference)
                for index_name in _dynamic_indices(reference):
                    if index_name not in generated:
                        required.add(index_name)
            if isinstance(node, IRAction) and node.store:
                generated.add(node.store)
            elif isinstance(node, (IRPredict, IRReact)):
                signature = self.skill_ir.signatures.get(node.signature)
                if signature and signature.output:
                    generated.add(signature.output.name)
        self.query_one("#run-input-editor", RunInputsEditor).load(sorted(required))

    def load_package(self, path: str | Path) -> None:
        package = load_package(path)
        self.skill_ir = package.ir
        self.tool_contracts = {tool.logical_id: tool for tool in package.tools}
        self.query_one("#skill-name", Input).value = package.name
        self.query_one("#skill-out", Input).value = str(path)
        self.dirty = False
        self.file_path = Path(path)
        self.valid = True
        self._clear_recovery_file()
        self._remember_recent(path)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.rebuild_tree()
        self._refresh_run_inputs()
        self._update_state()
        verification = package.manifest.verification.get("status", "unverified")
        self.write_status(f"Loaded compiled tree {path}. Verification: {verification}.")

    def open_definitions(self) -> None:
        self.app.push_screen(
            DefinitionsScreen(list(self.tool_contracts.values()), self.skill_ir),
            self._definitions_result,
        )

    def _definitions_result(self, contracts: list[ToolContract] | None) -> None:
        if contracts is None:
            return
        self.tool_contracts = {contract.logical_id: contract for contract in contracts}
        self._mark_dirty()
        self.write_status(f"Updated {len(contracts)} tool definition(s).")

    def _refresh_recent_files(self) -> None:
        recent = self.query_one("#recent-files", SelectionList)
        recent.clear_options()
        for path in self.app.settings.recent_files:
            recent.add_option((path, path))

    def _update_empty_state(self) -> None:
        if self.is_mounted:
            self.query_one("#empty-state").styles.display = (
                "block" if not self.skill_ir.root.children() else "none"
            )

    def _autosave_draft(self) -> None:
        if not self.is_mounted or not self.dirty:
            return
        path = recovery_path()
        temporary = path.with_suffix(".tmp")
        payload = {
            "ir": self.skill_ir.to_dict(),
            "signatures": {key: value.to_dict() for key, value in self.skill_ir.signatures.items()},
            "name": self._input("skill-name"),
            "output": self._input("skill-out"),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
            temporary.replace(path)
            self.query_one("#recovery-banner").styles.display = "block"
        except OSError as error:
            self.write_status(f"Draft autosave failed: {error}", severity="error")

    def recover_draft(self) -> None:
        try:
            payload = json.loads(recovery_path().read_text(encoding="utf-8"))
            signatures = {
                key: Signature.from_dict(value)
                for key, value in payload.get("signatures", {}).items()
            }
            self.skill_ir = BehaviorIR.from_dict(payload["ir"], signatures=signatures)
        except (OSError, KeyError, TypeError, ValueError) as error:
            self.write_status(f"Could not recover draft: {error}", severity="error")
            return
        self.selected_node = self.skill_ir.root
        self.query_one("#skill-name", Input).value = payload.get("name", "new-skill")
        self.query_one("#skill-out", Input).value = payload.get("output", "new-skill.jdsl")
        self.dirty = True
        self.valid = None
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.query_one("#recovery-banner").styles.display = "none"
        self.rebuild_tree()
        self._refresh_validation()
        self._refresh_run_inputs()
        self._update_state()
        self.write_status("Recovered autosaved draft.")

    def discard_recovery_draft(self) -> None:
        self._clear_recovery_file()
        self.write_status("Recovery draft discarded.")

    def _clear_recovery_file(self) -> None:
        try:
            recovery_path().unlink(missing_ok=True)
            if self.is_mounted:
                self.query_one("#recovery-banner").styles.display = "none"
        except OSError as error:
            self.write_status(f"Could not clear recovery draft: {error}", severity="warning")

    def _remember_recent(self, path: str | Path) -> None:
        resolved = str(Path(path).expanduser().resolve())
        recent = [item for item in self.app.settings.recent_files if item != resolved]
        self.app.settings.recent_files = [resolved, *recent][:10]
        self.app.settings.save()
        self._refresh_recent_files()

    def open_skill(self) -> None:
        path = self._input("open-path")
        if not path:
            start_path = str(Path.cwd())
            self.app.push_screen(OpenPackageScreen(start_path), self._open_dialog_result)
            return
        self.open_path(path)

    def _open_dialog_result(self, path: str | None) -> None:
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        if self.dirty:
            self.app.push_screen(
                ConfirmDiscardScreen(),
                lambda result: self._open_after_confirmation(result, path),
            )
            return
        self._open_path(path)

    def open_recent(self) -> None:
        selected = self.query_one("#recent-files", SelectionList).selected
        if not selected:
            self.write_status("Choose a recent package first.")
            return
        path = str(selected[0])
        self.open_path(path)

    def _open_after_confirmation(self, result: str | None, path: str) -> None:
        if result == "discard":
            self._open_path(path)

    def _open_path(self, path: str) -> None:
        try:
            self.load_package(path)
        except Exception as error:  # noqa: BLE001 - malformed packages are user input
            self.write_status(f"Could not open package: {error}", severity="error")

    def request_new_skill(self) -> None:
        self.app.push_screen(NewTemplateScreen(), self._template_selected)

    def _template_selected(self, template: str | None) -> None:
        if template is None:
            return
        if self.dirty:
            self.app.push_screen(
                ConfirmDiscardScreen(),
                lambda result: self._new_after_confirmation(result, template),
            )
            return
        self._reset_document(template)

    def _new_after_confirmation(self, result: str | None, template: str = "blank") -> None:
        if result == "discard":
            self._reset_document(template)

    def new_skill(self) -> None:
        self.request_new_skill()

    def _reset_document(self, template: str = "blank") -> None:
        root = IRSequence(type="sequence", id="root", children_=[])
        signatures: dict[str, Signature] = {}
        note = "Blank skill created."
        if template == "lookup-act":
            root.children_ = [
                IRAction(type="action", id="lookup", tool="lookup_customer", store="customer"),
                IRAction(
                    type="action", id="act", tool="update_record",
                    arguments={"customer_id": {"ref": "customer.id"}}, store="result",
                ),
            ]
            note = "Lookup-then-act template created with an exact blackboard ref."
        elif template == "predict":
            signature = Signature(
                id="decide", kind="predict",
                inputs={"request": SignatureInput(source="request")},
                output=SignatureOutput(name="decision"),
                instruction="Choose the next deterministic branch.",
            )
            signatures[signature.id] = signature
            root.children_.append(IRPredict(type="predict", id="decide", signature=signature.id))
            note = "Residual-decision template created; review its signature inputs and output."
        elif template == "guarded-write":
            root.children_ = [
                IRGuard(type="guard", id="confirmed", expression={"exists": "confirmation"}),
                IRAction(
                    type="action", id="write", tool="write_record",
                    arguments={"record": {"ref": "record"}},
                ),
            ]
            note = "Guarded-write template created; the write is sequenced after confirmation."
        self.skill_ir = BehaviorIR(root=root, signatures=signatures)
        self.tool_contracts.clear()
        self.selected_node = self.skill_ir.root
        self.file_path = None
        self.dirty = False
        self.valid = None
        self.runtime_status.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._clear_recovery_file()
        self.query_one("#skill-name", Input).value = "new-skill"
        self.query_one("#skill-out", Input).value = "new-skill.jdsl"
        self.rebuild_tree()
        self._update_state()
        self.write_status(note)

    def show_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def show_tour(self) -> None:
        self.app.push_screen(TourScreen(), self._tour_finished)

    def _tour_finished(self, _completed: bool | None) -> None:
        self.app.settings.tour_seen = True
        self.app.settings.save()

    def write_status(self, message: str, *, severity: str | None = None, notify: bool = False) -> None:
        self.query_one("#skill-status", Static).update(message)
        self.status(message)
        if notify:
            self.app.notify(message, severity=severity or "information", timeout=5)


__all__ = ["SkillWorkbench"]


def package_to_root(package: BehaviorPackage, tools: dict, predicates: dict, model_id: str):
    """Bind an in-memory package through the same verified runtime boundary."""
    return package_to_loaded(package).as_root(tools, predicates, model_id=model_id or None)


def package_to_loaded(package: BehaviorPackage):
    """Verify and load an in-memory package through the public package API."""
    return load_package_object(package)


def parse_inputs(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in value.split(","):
        if item.strip():
            if "=" not in item:
                raise ValueError(f"run input must be key=value: {item.strip()!r}")
            key, raw = item.split("=", 1)
            result[key.strip()] = raw.strip()
    return result
