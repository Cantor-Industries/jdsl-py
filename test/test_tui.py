"""Offline smoke tests for the skill authoring workbench."""

from __future__ import annotations

import asyncio
import hashlib

import pytest

from jdsl.ir import IRAction, IRGuard, IRPredict, IRSequence, Signature, SignatureInput, SignatureOutput
from jdsl.tui.commands import WorkbenchCommands
from jdsl.tui import SkillApp
from jdsl.tui.settings import TUISettings


@pytest.fixture(autouse=True)
def isolate_tui_user_data(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def test_tui_authors_and_reloads_predict_skill(tmp_path):
    output = tmp_path / "authored.jdsl"

    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.add_node("predict")
            child = pilot.app.query_one("#skill-tree").root.children[0]
            workbench.select_node(child)
            pilot.app.query_one("#node-id").value = "classify"
            pilot.app.query_one("#node-signature").value = "classify_request"
            await pilot.click("#signature-input-add")
            pilot.app.query_one("#signature-alias-0").value = "request"
            pilot.app.query_one("#signature-source-0").value = "request"
            pilot.app.query_one("#signature-output-name").value = "category"
            pilot.app.query_one("#signature-instruction").load_text("Classify the request.")
            workbench.apply_properties()
            assert workbench.selected_node is child.data
            assert pilot.app.query_one("#node-signature").value == "classify_request"
            assert workbench.validate_skill()
            pilot.app.query_one("#skill-name").value = "authored"
            pilot.app.query_one("#skill-out").value = str(output)
            workbench.save_skill()
            assert output.is_file()
            workbench.load_package(output)
            assert workbench.skill_ir.signatures["classify_request"].output.name == "category"

    asyncio.run(exercise())


def test_editing_signature_preserves_unexposed_metadata():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            node = IRPredict(type="predict", id="classify", signature="classify_request")
            signature = Signature(
                id="classify_request",
                inputs={"request": SignatureInput(source="blackboard.request", schema={"type": "object"})},
                output=SignatureOutput(name="category", schema={"type": "string", "enum": ["a", "b"]}),
                instruction="Old instruction",
                examples=[{"input": {"request": "hello"}, "output": {"category": "a"}}],
                context_policy={"model": "model-x", "max_examples": 4},
                validator={"type": "custom", "name": "keep-me"},
            )
            workbench.skill_ir.root.children_.append(node)
            workbench.skill_ir.signatures[signature.id] = signature
            workbench.rebuild_tree()
            workbench.select_node(pilot.app.query_one("#skill-tree").root.children[0])
            pilot.app.query_one("#signature-instruction").load_text("Updated instruction")

            workbench.apply_properties()

            updated = workbench.skill_ir.signatures["classify_request"]
            assert updated.instruction == "Updated instruction"
            assert updated.inputs["request"].source == "blackboard.request"
            assert updated.inputs["request"].schema == {"type": "object"}
            assert updated.output.schema == {"type": "string", "enum": ["a", "b"]}
            assert updated.examples == signature.examples
            assert updated.context_policy == {"model": "model-x", "max_examples": 4}
            assert updated.validator == {"type": "custom", "name": "keep-me"}

    asyncio.run(exercise())


def test_tui_starts_in_authoring_workspace():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            assert pilot.app.query_one("#skill-workspace") is pilot.app.skill_workbench
            assert pilot.app.query_one("#skill-tree")
            assert not pilot.app.query("#captures")

    asyncio.run(exercise())


def test_tui_shows_validation_status():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            pilot.app.skill_workbench.validate_skill()
            status = pilot.app.query_one("#skill-status")
            assert "Validation failed" in str(status.render())

    asyncio.run(exercise())


def test_validate_button_updates_status():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            await pilot.click("#validate-skill")
            status = pilot.app.query_one("#skill-status")
            assert "Validation failed" in str(status.render())

    asyncio.run(exercise())


def test_node_edits_can_be_undone_and_redone():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.add_node("action")
            assert len(workbench.skill_ir.root.children()) == 1

            workbench.undo()
            assert workbench.skill_ir.root.children() == []

            workbench.redo()
            assert len(workbench.skill_ir.root.children()) == 1

    asyncio.run(exercise())


def test_repeat_child_can_be_removed_and_ids_stay_unique():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.add_node("repeat")
            repeat = workbench.skill_ir.root.children()[0]
            workbench.select_node(pilot.app.query_one("#skill-tree").root.children[0])
            workbench.add_node("action")
            action = repeat.child
            workbench.select_node(pilot.app.query_one("#skill-tree").root.children[0].children[0])
            workbench.remove_selected_node()
            assert repeat.child is None

            workbench.add_node("action")
            workbench.add_node("action")
            ids = [node.id for node in workbench.skill_ir.walk() if node.id]
            assert len(ids) == len(set(ids))
            assert action is not None

    asyncio.run(exercise())


def test_workbench_preferences_persist(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    settings = TUISettings(reduced_motion=True, ascii_glyphs=False)
    settings.save()

    assert TUISettings.load() == settings


def test_run_confirms_tools_and_executes_in_worker(monkeypatch, tmp_path):
    async def exercise() -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        tools_path = tmp_path / "tools.py"
        tools_path.write_text('TOOLS = {"echo": lambda: "ok"}\n', encoding="utf-8")
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.skill_ir.root.children_.append(
                IRAction(type="action", id="echo", tool="echo", store="answer")
            )
            workbench.rebuild_tree()
            pilot.app.query_one("#run-tools").value = str(tools_path)

            workbench.run_skill()
            await pilot.pause()
            assert pilot.app.screen.__class__.__name__ == "TrustToolsScreen"
            await pilot.click("#trust-tools")
            worker = workbench._run_worker
            await worker.wait()
            await pilot.pause()

            assert workbench.runtime_status["echo"] == "success"
            assert "Run complete" in str(pilot.app.query_one("#skill-status").render())

    asyncio.run(exercise())


def test_run_inputs_are_generated_from_unresolved_refs():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.skill_ir.root.children_ = [
                IRAction(type="action", id="list", tool="list", store="orders"),
                IRAction(
                    type="action",
                    id="get",
                    tool="get",
                    arguments={"order_id": {"ref": "orders[$selected_index].id"}},
                ),
            ]
            workbench._refresh_run_inputs()
            editor = pilot.app.query_one("#run-input-editor")
            assert pilot.app.query_one("#run-input-name-0").value == "selected_index"
            editor.query_one("#run-input-value-0").value = "2"
            assert editor.value() == {"selected_index": 2}

    asyncio.run(exercise())


def test_dry_run_reports_intent_without_calling_tools(monkeypatch, tmp_path):
    async def exercise() -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        marker = tmp_path / "tool-called"
        tools_path = tmp_path / "tools.py"
        tools_path.write_text(
            "from pathlib import Path\n"
            f"def write(): Path({str(marker)!r}).write_text('called')\n"
            "TOOLS = {'write': write}\n",
            encoding="utf-8",
        )
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.skill_ir.root.children_.append(
                IRAction(type="action", id="write", tool="write", store="result")
            )
            workbench.rebuild_tree()
            pilot.app.query_one("#run-tools").value = str(tools_path)
            pilot.app.query_one("#dry-run").value = True

            workbench.run_skill()
            await pilot.pause()
            await pilot.click("#trust-tools")
            await workbench._run_worker.wait()
            await pilot.pause()

            assert not marker.exists()
            assert "Dry run" in str(pilot.app.query_one("#skill-status").render())
            assert pilot.app.query_one("#run-panel").intended_calls == ["write"]

    asyncio.run(exercise())


def test_stop_request_prevents_next_tool_call(monkeypatch, tmp_path):
    async def exercise() -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        marker = tmp_path / "tool-called"
        tools_path = tmp_path / "tools.py"
        tools_path.write_text(
            "from pathlib import Path\n"
            f"def write(): Path({str(marker)!r}).write_text('called')\n"
            "TOOLS = {'write': write}\n",
            encoding="utf-8",
        )
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.skill_ir.root.children_.append(
                IRAction(type="action", id="write", tool="write")
            )
            workbench.rebuild_tree()
            digest = hashlib.sha256(tools_path.read_bytes()).hexdigest()
            workbench._trust_tools_result(True, tools_path=tools_path, digest=digest)
            workbench.cancel_run()
            await workbench._run_worker.wait()
            await pilot.pause()

            assert not marker.exists()
            assert "Run cancelled" in str(pilot.app.query_one("#skill-status").render())

    asyncio.run(exercise())


def test_move_indent_duplicate_copy_and_undo():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            group = IRSequence(type="sequence", id="group", children_=[])
            first = IRAction(type="action", id="first", tool="a")
            second = IRAction(type="action", id="second", tool="b")
            workbench.skill_ir.root.children_ = [group, first, second]
            workbench.rebuild_tree()
            tree = pilot.app.query_one("#skill-tree")
            workbench.select_node(tree.root.children[2])
            workbench.move_selected(-1)
            assert [node.id for node in workbench.skill_ir.root.children()] == ["group", "second", "first"]

            workbench.select_node(tree.root.children[1])
            workbench.indent_selected()
            assert group.children() == [second]
            workbench.outdent_selected()
            assert workbench.skill_ir.root.children()[1] is second

            workbench.copy_selected_node()
            workbench.paste_node()
            pasted = workbench.skill_ir.root.children()[2]
            assert pasted.id not in {"group", "first", "second"}
            workbench.undo()
            assert len(workbench.skill_ir.root.children()) == 3

    asyncio.run(exercise())


def test_tree_expansion_and_search_survive_rebuild():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            nested = IRSequence(
                type="sequence",
                id="nested",
                children_=[IRAction(type="action", id="lookup", tool="lookup")],
            )
            workbench.skill_ir.root.children_.append(nested)
            workbench.rebuild_tree()
            tree = pilot.app.query_one("#skill-tree")
            tree.root.children[0].expand()
            workbench.rebuild_tree()
            assert tree.root.children[0].is_expanded
            assert workbench.jump_to_node("lookup")
            assert workbench.selected_node.id == "lookup"

    asyncio.run(exercise())


def test_command_palette_provider_discovers_workbench_actions():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            provider = WorkbenchCommands(pilot.app.screen)
            discovered = [hit async for hit in provider.discover()]
            assert any(hit.text == "Add action" for hit in discovered)
            matches = [hit async for hit in provider.search("undo")]
            assert any(hit.text == "Undo" for hit in matches)

    asyncio.run(exercise())


def test_save_dialog_exports_verifies_and_remembers_recent(tmp_path):
    async def exercise() -> None:
        output = tmp_path / "saved.jdsl"
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.skill_ir.root.children_.append(
                IRAction(type="action", id="lookup", tool="lookup")
            )
            workbench.rebuild_tree()
            workbench.request_save()
            await pilot.pause()
            assert pilot.app.screen.__class__.__name__ == "SavePackageScreen"
            pilot.app.screen.query_one("#save-name").value = "saved-skill"
            pilot.app.screen.query_one("#save-version").value = "1.2.0"
            pilot.app.screen.query_one("#save-output").value = str(output)
            pilot.app.screen.query_one("#save-description").value = "Saved from Pilot."
            await pilot.click("#confirm-save")
            await pilot.pause()

            assert output.is_file()
            assert workbench.dirty is False
            assert pilot.app.settings.recent_files[0] == str(output.resolve())

    asyncio.run(exercise())


def test_new_templates_and_recovery_draft(tmp_path):
    async def exercise() -> None:
        async with SkillApp().run_test() as first_pilot:
            workbench = first_pilot.app.skill_workbench
            workbench._reset_document("lookup-act")
            assert [node.id for node in workbench.skill_ir.root.children()] == ["lookup", "act"]
            assert workbench.skill_ir.root.children()[1].arguments == {
                "customer_id": {"ref": "customer.id"}
            }
            workbench._mark_dirty()

        async with SkillApp().run_test() as second_pilot:
            workbench = second_pilot.app.skill_workbench
            assert second_pilot.app.query_one("#recovery-banner").styles.display == "block"
            workbench.recover_draft()
            assert workbench.dirty
            assert [node.id for node in workbench.skill_ir.root.children()] == ["lookup", "act"]
            workbench._clear_recovery_file()

    asyncio.run(exercise())


def test_help_and_template_picker_are_reachable():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.show_help()
            await pilot.pause()
            assert pilot.app.screen.__class__.__name__ == "HelpScreen"
            await pilot.press("escape")
            await pilot.pause()
            workbench.request_new_skill()
            await pilot.pause()
            assert pilot.app.screen.__class__.__name__ == "NewTemplateScreen"

    asyncio.run(exercise())


def test_open_uses_directory_picker_and_recent_open_is_guarded(tmp_path):
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.open_skill()
            await pilot.pause()
            assert pilot.app.screen.__class__.__name__ == "OpenPackageScreen"
            await pilot.press("escape")
            await pilot.pause()

            workbench.add_node("sequence")
            workbench.app.settings.recent_files = [str(tmp_path / "recent.jdsl")]
            workbench.open_path(workbench.app.settings.recent_files[0])
            await pilot.pause()
            assert pilot.app.screen.__class__.__name__ == "ConfirmDiscardScreen"

    asyncio.run(exercise())


def test_definitions_edit_tool_effects_and_schemas():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.skill_ir.root.children_.append(
                IRAction(type="action", id="delete", tool="delete_customer")
            )
            workbench.open_definitions()
            await pilot.pause()
            screen = pilot.app.screen
            screen.query_one("#definition-id").value = "delete_customer"
            screen.query_one("#definition-description").value = "Delete a customer record"
            screen.query_one("#definition-arguments").value = "customer_id, reason"
            screen.query_one("#definition-effect").value = "destructive"
            await pilot.click("#definition-save")
            await pilot.click("#definitions-done")
            await pilot.pause()

            contract = workbench.tool_contracts["delete_customer"]
            assert contract.effects.destructive
            assert contract.input_schema["required"] == ["customer_id", "reason"]
            assert contract.description == "Delete a customer record"
            package = workbench._build_package("toolbox", "1.0.0", "")
            assert package.tools[0].effects.destructive

    asyncio.run(exercise())


def test_inspector_live_applies_and_quit_prompts_for_dirty_document():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.add_node("action")
            action_node = pilot.app.query_one("#skill-tree").root.children[0]
            workbench.select_node(action_node)
            pilot.app.query_one("#node-tool").value = "lookup"
            await pilot.pause(0.5)

            assert workbench.selected_node.tool == "lookup"
            assert workbench.dirty
            assert "RDB 0.00" in str(pilot.app.query_one("#skill-state").render())
            assert workbench.valid
            assert "No problems" in str(pilot.app.query_one("#skill-problems").render())

            await pilot.press("q")
            await pilot.pause()
            assert pilot.app.screen.__class__.__name__ == "ConfirmDiscardScreen"

    asyncio.run(exercise())


def test_structured_arguments_round_trip_refs_and_literals():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.add_node("action")
            workbench.select_node(pilot.app.query_one("#skill-tree").root.children[0])
            editor = pilot.app.query_one("#action-arguments")
            editor.load({
                "customer_id": {"ref": "customer.id"},
                "choice": {"ref": "orders[$selected_index].id"},
                "active": {"const": True},
            })

            assert editor.value() == {
                "customer_id": {"ref": "customer.id"},
                "choice": {"ref": "orders[$selected_index].id"},
                "active": {"const": True},
            }

    asyncio.run(exercise())


def test_guard_builder_and_raw_fallback_are_safe():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            workbench = pilot.app.skill_workbench
            workbench.add_node("guard")
            workbench.select_node(pilot.app.query_one("#skill-tree").root.children[0])
            editor = pilot.app.query_one("#guard-fields")
            expression = {"eq": [{"ref": "confirmation.state"}, "confirmed"]}
            editor.load(expression)
            assert editor.value() == expression

            nested = {"and": [{"exists": "order"}, {"not": {"exists": "refund"}}]}
            editor.load(nested)
            assert editor.query_one("#guard-tabs").active == "guard-raw-pane"
            assert editor.value() == nested

            editor.query_one("#guard-tabs").active = "guard-raw-pane"
            editor.query_one("#node-expression-raw").load_text("{invalid")
            try:
                editor.value()
            except ValueError as error:
                assert "guard JSON" in str(error)
            else:
                raise AssertionError("invalid raw guard JSON was accepted")

    asyncio.run(exercise())


def test_oversized_argument_set_uses_lossless_raw_tab():
    async def exercise() -> None:
        async with SkillApp().run_test() as pilot:
            editor = pilot.app.query_one("#action-arguments")
            arguments = {f"arg_{index}": {"const": index} for index in range(15)}
            editor.load(arguments)

            assert editor.query_one("#arguments-tabs").active == "arguments-raw-pane"
            assert editor.value() == arguments

    asyncio.run(exercise())
