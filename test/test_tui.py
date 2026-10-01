"""Offline smoke tests for the skill authoring workbench."""

from __future__ import annotations

import asyncio

from jdsl.tui import SkillApp


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
            pilot.app.query_one("#signature-inputs").value = "request"
            pilot.app.query_one("#signature-output").value = "category"
            pilot.app.query_one("#signature-instructions").value = "Classify the request."
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
