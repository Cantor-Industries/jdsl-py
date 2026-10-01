"""Skill authoring workbench used by the Textual TUI."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Static, Tree
from textual.widgets.tree import TreeNode

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
    package_digest,
)
from jdsl.trace.sink import ListTraceSink


class SkillWorkbench(Vertical):
    """IR-backed tree editor for authored and compiled JDSL skills."""

    def __init__(self, *, status: Callable[[str], None] | None = None) -> None:
        super().__init__(id="skill-workspace")
        self.status = status or (lambda _message: None)
        self.skill_ir = BehaviorIR(root=IRSequence(type="sequence", id="root", children_=[]))
        self.selected_node: IRNode = self.skill_ir.root
        self._tree_node: TreeNode[IRNode] | None = None
        self.runtime_status: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Static("Select a node, configure it, then validate or run.", id="skill-status")
        with Horizontal(id="skill-tree-panel"):
            with Vertical():
                yield Static("SKILL TREE", classes="panel-title")
                yield Tree("root", id="skill-tree")
                with Horizontal(id="skill-actions"):
                    with Horizontal(classes="action-row"):
                        for node_type in ("sequence", "selector", "action", "guard"):
                            yield Button(f"+ {node_type}", id=f"add-{node_type}")
                    with Horizontal(classes="action-row"):
                        for node_type in ("predict", "react", "repeat"):
                            yield Button(f"+ {node_type}", id=f"add-{node_type}")
                        yield Button("Remove", id="remove-node")
            with Vertical(id="skill-properties-panel"):
                yield Static("NODE PROPERTIES", classes="panel-title")
                with VerticalScroll(id="skill-properties-scroll"):
                    with Vertical(id="skill-properties"):
                        yield Label("Select a node")
                        with Horizontal(classes="field-row"):
                            yield Input(placeholder="Node id", id="node-id")
                            yield Input(placeholder="Tool capability", id="node-tool")
                        with Horizontal(classes="field-row"):
                            yield Input(placeholder="Store result as", id="node-store")
                            yield Input(placeholder="Repeat max", id="repeat-max")
                        with Horizontal(classes="field-row"):
                            yield Input(placeholder="Action arguments JSON", id="node-arguments")
                            yield Input(placeholder="Guard expression JSON", id="node-expression")
                        with Horizontal(classes="field-row"):
                            yield Input(placeholder="Signature id", id="node-signature")
                            yield Input(placeholder="Model / provider", id="node-model")
                        with Horizontal(classes="field-row"):
                            yield Input(placeholder="Inputs, comma separated", id="signature-inputs")
                            yield Input(placeholder="Output field", id="signature-output")
                        yield Input(placeholder="Instructions", id="signature-instructions")
                        yield Input(placeholder="Allowed tools, comma separated", id="signature-tools")
                        with Horizontal(classes="field-row"):
                            yield Input(placeholder="Package name", value="new-skill", id="skill-name")
                            yield Input(placeholder="Output path", value="new-skill.jdsl", id="skill-out")
                        with Horizontal(classes="field-row"):
                            yield Input(placeholder="Tools module path (defines TOOLS)", id="run-tools")
                            yield Input(placeholder="Run model id", id="run-model")
                        yield Input(placeholder="Run inputs: key=value, ...", id="run-inputs")
                with Horizontal(classes="actions"):
                    yield Button("Apply", id="apply-properties", variant="primary")
                    yield Button("Validate", id="validate-skill")
                    yield Button("Save", id="save-skill", variant="success")
                    yield Button("Run", id="run-skill", variant="primary")

    def on_mount(self) -> None:
        self.rebuild_tree()

    @staticmethod
    def node_label(node: IRNode) -> str:
        detail = ""
        if isinstance(node, IRAction):
            detail = f" {node.tool or '(tool)'}"
        elif isinstance(node, (IRPredict, IRReact)):
            detail = f" {node.signature or '(signature)'}"
        return f"{node.type}{detail}" + (f"  #{node.id}" if node.id else "")

    def display_label(self, node: IRNode) -> str:
        status = self.runtime_status.get(node.id or "")
        prefix = {"success": "[ok] ", "failure": "[!!] "}.get(status, "")
        return prefix + self.node_label(node)

    def rebuild_tree(self) -> None:
        selected = self.selected_node
        tree = self.query_one("#skill-tree", Tree)
        tree.clear()
        root = tree.root
        root.label = self.display_label(self.skill_ir.root)
        root.data = self.skill_ir.root
        self._add_children(root, self.skill_ir.root)
        root.expand()
        self.select_node(self._find_tree_node(root, selected) or root)

    def _add_children(self, parent: TreeNode[IRNode], node: IRNode) -> None:
        for child in node.children():
            child_node = parent.add(self.display_label(child), data=child)
            self._add_children(child_node, child)

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
        return self.query_one(f"#{field}", Input).value.strip()

    def _csv(self, field: str) -> list[str]:
        return [value.strip() for value in self._input(field).split(",") if value.strip()]

    def populate_properties(self, node: IRNode) -> None:
        signature = self.skill_ir.signatures.get(node.signature) if isinstance(node, (IRPredict, IRReact)) else None
        values = {
            "node-id": node.id or "",
            "node-tool": node.tool if isinstance(node, IRAction) else "",
            "node-store": node.store if isinstance(node, IRAction) else "",
            "node-arguments": json.dumps(node.arguments, sort_keys=True) if isinstance(node, IRAction) else "",
            "node-expression": json.dumps(node.expression, sort_keys=True) if isinstance(node, IRGuard) else "",
            "node-signature": node.signature if isinstance(node, (IRPredict, IRReact)) else "",
            "node-model": signature.context_policy.get("model", "") if signature else "",
            "signature-inputs": ", ".join(signature.inputs) if signature else "",
            "signature-output": signature.output.name if signature and signature.output else "",
            "signature-instructions": signature.instruction if signature else "",
            "signature-tools": ", ".join(signature.tools) if signature else "",
            "repeat-max": str(node.max) if isinstance(node, IRRepeat) else "",
        }
        for field, value in values.items():
            self.query_one(f"#{field}", Input).value = value

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
            self.save_skill()
        elif button_id == "run-skill":
            self.run_skill()

    def add_node(self, node_type: str) -> None:
        parent = self.selected_node if isinstance(self.selected_node, (IRComposite, IRRepeat)) else self.skill_ir.root
        node_id = f"{node_type}_{len(self.skill_ir.walk())}"
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
        if isinstance(parent, IRRepeat) and parent.child is None:
            parent.child = new_node
        else:
            parent.children_.append(new_node)
        self.rebuild_tree()
        self.write_status(f"Added {node_type} under {parent.type}. Configure it in the properties panel.")

    def apply_properties(self) -> None:
        node = self.selected_node
        node.id = self._input("node-id") or None
        if isinstance(node, IRAction):
            node.tool = self._input("node-tool")
            node.store = self._input("node-store") or None
            try:
                node.arguments = json.loads(self._input("node-arguments") or "{}")
            except json.JSONDecodeError as error:
                self.write_status(f"Action arguments must be valid JSON: {error.msg}.")
                return
        if isinstance(node, IRGuard):
            try:
                node.expression = json.loads(self._input("node-expression") or "{}")
            except json.JSONDecodeError as error:
                self.write_status(f"Guard expression must be valid JSON: {error.msg}.")
                return
        if isinstance(node, (IRPredict, IRReact)):
            signature_id = self._input("node-signature") or f"sig_{node.id or node.type}"
            node.signature = signature_id
            model = self._input("node-model")
            self.skill_ir.signatures[signature_id] = Signature(
                id=signature_id,
                kind="react" if isinstance(node, IRReact) else "predict",
                inputs={name: SignatureInput(source=name) for name in self._csv("signature-inputs")},
                output=SignatureOutput(name=self._input("signature-output") or "answer"),
                instruction=self._input("signature-instructions"),
                tools=self._csv("signature-tools"),
                context_policy={"model": model} if model else {},
            )
        if isinstance(node, IRRepeat):
            try:
                node.max = int(self._input("repeat-max") or "3")
            except ValueError:
                self.write_status("Repeat max must be an integer.")
                return
        self.rebuild_tree()
        self.write_status(f"Applied properties to {node.type}.")

    def remove_selected_node(self) -> None:
        if self.selected_node is self.skill_ir.root:
            self.write_status("The root node cannot be removed.")
            return
        if self._remove_from(self.skill_ir.root, self.selected_node):
            self.rebuild_tree()
            self.write_status("Removed selected node.")

    def _remove_from(self, parent: IRNode, target: IRNode) -> bool:
        if isinstance(parent, IRComposite) and target in parent.children_:
            parent.children_.remove(target)
            return True
        return any(self._remove_from(child, target) for child in parent.children())

    def _capabilities(self) -> set[str]:
        caps = {node.tool for node in self.skill_ir.walk() if isinstance(node, IRAction) and node.tool}
        caps.update(
            tool for signature in self.skill_ir.signatures.values()
            if signature.kind == "react" for tool in signature.tools
        )
        return caps

    def validate_skill(self) -> bool:
        report = validate_ir(self.skill_ir, required_capabilities=self._capabilities())
        if report.ok:
            self.write_status("Valid behavior tree. Ready to save.")
            return True
        self.write_status("Validation failed: " + "; ".join(report.problems))
        return False

    def save_skill(self) -> None:
        if not self.validate_skill():
            return
        name = self._input("skill-name") or "new-skill"
        output = self._input("skill-out") or f"{name}.jdsl"
        package = BehaviorPackage(
            manifest=Manifest(name=name, required_capabilities=sorted(self._capabilities()),
                              source={"authoring": "jdsl-tui"}),
            ir=self.skill_ir,
            tools=[ToolContract(logical_id=capability) for capability in sorted(self._capabilities())],
            readme=f"# {name}\n\nAuthored in the JDSL TUI.\n",
        )
        path = export_jdsl(package, Path(output))
        load_package(path)
        self.write_status(f"Saved and verified {path} ({package_digest(package)[:24]}...).")

    def run_skill(self) -> None:
        tools_path = self._input("run-tools")
        if not tools_path:
            self.write_status("Run requires a Python tools module defining TOOLS.")
            return
        try:
            spec = importlib.util.spec_from_file_location("jdsl_tui_tools", tools_path)
            if spec is None or spec.loader is None:
                raise ValueError(f"cannot import {tools_path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            tools = getattr(module, "TOOLS", None)
            if not isinstance(tools, dict):
                raise ValueError("tools module must define a TOOLS dict")
            package = BehaviorPackage(
                manifest=Manifest(name=self._input("skill-name") or "new-skill",
                                  required_capabilities=sorted(self._capabilities())),
                ir=self.skill_ir,
                tools=[ToolContract(logical_id=capability) for capability in sorted(self._capabilities())],
            )
            root = package_to_root(package, tools, getattr(module, "PREDICATES", {}), self._input("run-model"))
            inputs = parse_inputs(self._input("run-inputs"))
            sink = ListTraceSink()
            ctx = root.run(trace_sink=sink, **inputs)
            self.runtime_status = {
                str(event.payload["node_id"]): event.payload["status"]
                for event in sink.events
                if "node_id" in event.payload and "status" in event.payload
            }
            self.rebuild_tree()
            self.write_status(f"Run complete. Blackboard: {dict(ctx.blackboard)}")
        except Exception as error:  # noqa: BLE001 - display user-facing run failures
            self.write_status(f"Run failed: {error}")

    def load_package(self, path: str | Path) -> None:
        package = load_package(path)
        self.skill_ir = package.ir
        self.query_one("#skill-name", Input).value = package.name
        self.query_one("#skill-out", Input).value = str(path)
        self.rebuild_tree()
        verification = package.manifest.verification.get("status", "unverified")
        self.write_status(f"Loaded compiled tree {path}. Verification: {verification}.")

    def write_status(self, message: str) -> None:
        self.query_one("#skill-status", Static).update(message)
        self.status(message)
        severity = "error" if "failed" in message.lower() else "information"
        self.app.notify(message, severity=severity, timeout=5)


__all__ = ["SkillWorkbench"]


def package_to_root(package: BehaviorPackage, tools: dict, predicates: dict, model_id: str):
    """Bind an in-memory package through the same verified runtime boundary."""
    return package_to_loaded(package).as_root(tools, predicates, model_id=model_id or None)


def package_to_loaded(package: BehaviorPackage):
    """Round-trip through the package loader's validation contract in memory."""
    from jdsl.ir.validate import validate_ir
    report = validate_ir(package.ir, required_capabilities=set(package.manifest.required_capabilities))
    if not report.ok:
        raise ValueError("invalid behavior: " + "; ".join(report.problems))
    from jdsl.package.load import LoadedPackage
    return LoadedPackage(package.manifest, package.ir, package.tools, package.provenance)


def parse_inputs(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in value.split(","):
        if item.strip():
            if "=" not in item:
                raise ValueError(f"run input must be key=value: {item.strip()!r}")
            key, raw = item.split("=", 1)
            result[key.strip()] = raw.strip()
    return result
