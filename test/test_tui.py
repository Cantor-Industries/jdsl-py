"""Offline smoke tests for the harness dashboard."""

from __future__ import annotations

import asyncio

from jdsl.tui import HarnessApp


def test_tui_capture_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("JDSL_HARNESS_HOME", str(tmp_path / "harness"))

    async def exercise() -> None:
        async with HarnessApp().run_test() as pilot:
            pilot.app.new_capture()
            assert pilot.app.active_capture is not None
            pilot.app.finish_capture()
            assert pilot.app.active_capture is None
            assert pilot.app.store.list_captures()[0]["status"] == "finished"


def test_tui_stops_server_after_capture_finishes(tmp_path, monkeypatch):
    monkeypatch.setenv("JDSL_HARNESS_HOME", str(tmp_path / "harness"))

    async def exercise() -> None:
        async with HarnessApp().run_test() as pilot:
            pilot.app.start_server()
            assert pilot.app.server is not None
            pilot.app.new_capture()
            pilot.app.stop_server()
            assert pilot.app.server is not None
            pilot.app.finish_capture()
            pilot.app.stop_server()
            assert pilot.app.server is None

    asyncio.run(exercise())

    asyncio.run(exercise())
