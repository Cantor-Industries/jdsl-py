"""Textual dashboard for the local JDSL harness."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, RichLog, Static

from jdsl_harness.capture import CaptureCoordinator
from jdsl_harness.server import IngestServer
from jdsl_harness.store import HarnessStore


class HarnessApp(App[None]):
    """Operations console over the existing harness control plane."""

    CSS = """
    Screen {
        background: #101417;
        color: #d8e1df;
        layout: vertical;
    }
    Header { background: #17211f; color: #d8e1df; }
    #brand {
        height: 7;
        padding: 1 2;
        background: #182a25;
        border: tall #5ee6a8;
        color: #d8e1df;
        opacity: 0;
    }
    .brand-title { color: #5ee6a8; text-style: bold; }
    .brand-subtitle { color: #9cb2aa; }
    #status-row { height: 5; margin: 1 0; }
    .status-card {
        width: 1fr;
        height: 5;
        margin-right: 1;
        padding: 1 2;
        background: #18201f;
        border: round #2f4d43;
    }
    .status-card:last-child { margin-right: 0; }
    .status-label { color: #8da59c; text-style: bold; }
    .status-value { color: #f1f7f4; }
    #workspace { height: 1fr; }
    #capture-panel, #package-panel {
        width: 1fr;
        height: 1fr;
        padding: 1;
        background: #141b1a;
        border: round #2f4d43;
    }
    #capture-panel { margin-right: 1; }
    .panel-title { color: #5ee6a8; text-style: bold; padding-bottom: 1; }
    #captures { height: 1fr; border: none; }
    #capture-hint { height: 2; color: #8da59c; }
    #controls { height: auto; margin-top: 1; }
    #controls Input { width: 1fr; margin-right: 1; }
    #controls Input:last-child { margin-right: 0; }
    .actions { height: auto; padding: 1 0; }
    .actions Button { margin-right: 1; }
    .actions Button.-primary { background: #237a57; }
    #stop-server { background: #743f45; }
    #log { height: 9; padding: 1; background: #0e1314; border: round #2f4d43; }
    Footer { background: #17211f; }
    DataTable > .datatable--header { background: #20342d; color: #bcefd4; }
    DataTable:focus { border: tall #5ee6a8; }
    """

    BINDINGS = [("q", "quit", "Quit"), ("r", "refresh", "Refresh")]

    def __init__(self) -> None:
        super().__init__()
        root = Path(os.environ.get("JDSL_HARNESS_HOME") or (Path.home() / ".local/share/jdsl-harness"))
        self.store = HarnessStore(root)
        self.coordinator = CaptureCoordinator(self.store)
        self.server: IngestServer | None = None
        self.active_capture: str | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="brand"):
            yield Static("      _     ____  ____  _     ", classes="brand-title")
            yield Static(r"     | |   |  _ \/ ___|| |    ", classes="brand-title")
            yield Static(r"  J D S L   | | | \___ \| |    ", classes="brand-title")
            yield Static("     |_|   |_| |_|____) | |___ ", classes="brand-title")
            yield Static("behavior operations console", classes="brand-subtitle")
        with Horizontal(id="status-row"):
            with Vertical(classes="status-card"):
                yield Label("INGEST SERVER", classes="status-label")
                yield Static("STOPPED", id="server-status", classes="status-value")
            with Vertical(classes="status-card"):
                yield Label("CAPTURE", classes="status-label")
                yield Static("NONE", id="capture-status", classes="status-value")
            with Vertical(classes="status-card"):
                yield Label("STORE", classes="status-label")
                yield Static("~/.local/share/jdsl-harness", id="store-status", classes="status-value")
        with Horizontal(id="workspace"):
            with Vertical(id="capture-panel"):
                yield Static("CAPTURES", classes="panel-title")
                yield DataTable(id="captures", cursor_type="row")
                yield Static("Select a capture row to inspect or compile it.", id="capture-hint")
            with Vertical(id="package-panel"):
                yield Static("PACKAGE WORKBENCH", classes="panel-title")
                with Vertical(id="controls"):
                    yield Input(placeholder="Capture id", id="capture-id")
                    yield Input(placeholder="Package name", value="behavior", id="package-name")
                    yield Input(placeholder="Output path", value="behavior.jdsl", id="package-out")
                with Horizontal(classes="actions"):
                    yield Button("Start server", id="start-server", variant="primary")
                    yield Button("Stop server", id="stop-server")
                with Horizontal(classes="actions"):
                    yield Button("New capture", id="new-capture")
                    yield Button("Finish capture", id="finish-capture")
                with Horizontal(classes="actions"):
                    yield Button("Inspect", id="inspect")
                    yield Button("Compile", id="compile", variant="success")
        yield RichLog(id="log", markup=False, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#captures", DataTable)
        table.add_columns("Capture", "Status", "Episodes", "Host")
        self.refresh_dashboard()
        self.write_log("Ready. Start the server before launching a host plugin.")
        self.query_one("#brand").styles.animate("opacity", value=1.0, duration=0.35)

    def action_refresh(self) -> None:
        self.refresh_dashboard()

    def write_log(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def refresh_dashboard(self) -> None:
        captures = self.store.list_captures()
        table = self.query_one("#captures", DataTable)
        table.clear(columns=False)
        for row in captures:
            table.add_row(row["capture_id"], row["status"], str(row["episodes"]), row.get("host") or "unknown")
        server_value = self.server.url if self.server else "STOPPED"
        capture_value = self.active_capture or "NONE"
        self.query_one("#server-status", Static).update(server_value)
        self.query_one("#capture-status", Static).update(capture_value)
        self.query_one("#store-status", Static).update(str(self.store.root))
        self.query_one("#start-server", Button).disabled = self.server is not None
        self.query_one("#stop-server", Button).disabled = self.server is None
        self.query_one("#new-capture", Button).disabled = self.server is None or self.active_capture is not None
        self.query_one("#finish-capture", Button).disabled = self.active_capture is None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        capture_id = str(event.row_key.value)
        self.query_one("#capture-id", Input).value = capture_id
        self.write_log(f"Selected capture {capture_id}")

    def selected_capture(self) -> str | None:
        value = self.query_one("#capture-id", Input).value.strip()
        return value or self.active_capture

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "start-server": self.start_server,
            "stop-server": self.stop_server,
            "new-capture": self.new_capture,
            "finish-capture": self.finish_capture,
            "inspect": self.inspect_capture,
            "compile": self.compile_capture,
        }
        handler = handlers.get(event.button.id or "")
        if handler:
            handler()

    def start_server(self) -> None:
        if self.server:
            self.write_log(f"Server already running at {self.server.url}")
            return
        try:
            self.server = IngestServer(self.store, port=8848).start()
        except OSError as err:
            self.write_log(f"Port 8848 is unavailable ({err}); selecting an open port.")
            try:
                self.server = IngestServer(self.store, port=0).start()
            except OSError as fallback_err:
                self.write_log(f"Could not start ingest server: {fallback_err}")
                return
        self.write_log(f"Ingest server listening at {self.server.url}")
        self.write_log(f"Set JDSL_INGEST_URL={self.server.url} in the host environment.")
        self.refresh_dashboard()

    def stop_server(self) -> None:
        if not self.server:
            self.write_log("Server is already stopped.")
            return
        if self.active_capture:
            self.write_log("Finish the active capture before stopping the server.")
            return
        url = self.server.url
        self.server.stop()
        self.server = None
        self.write_log(f"Stopped ingest server at {url}")
        self.refresh_dashboard()

    def new_capture(self) -> None:
        if self.active_capture:
            self.write_log(f"Capture already active: {self.active_capture}")
            return
        self.active_capture = self.coordinator.start(host="host", adapter="tui")
        self.query_one("#capture-id", Input).value = self.active_capture
        self.write_log(f"Started capture {self.active_capture}")
        self.refresh_dashboard()

    def finish_capture(self) -> None:
        capture_id = self.selected_capture()
        if not capture_id:
            self.write_log("No capture selected.")
            return
        self.coordinator.finish(capture_id)
        if capture_id == self.active_capture:
            self.active_capture = None
        self.write_log(f"Finished capture {capture_id}")
        self.refresh_dashboard()

    def inspect_capture(self) -> None:
        capture_id = self.selected_capture()
        if not capture_id:
            self.write_log("No capture selected.")
            return
        report = self.coordinator.lineage_report(capture_id)
        self.write_log(
            f"{capture_id}: episodes={len(report['episodes'])}, "
            f"deterministic={len(report['deterministic_candidates'])}, "
            f"residual={len(report['residual_candidates'])}"
        )

    def compile_capture(self) -> None:
        capture_id = self.selected_capture()
        if not capture_id:
            self.write_log("No capture selected.")
            return
        from jdsl.package import export_jdsl, package_digest
        from jdsl_harness.compiler import compile_behavior

        name = self.query_one("#package-name", Input).value.strip() or "behavior"
        output = self.query_one("#package-out", Input).value.strip() or f"{name}.jdsl"
        try:
            result = compile_behavior(self.store.capture_episodes(capture_id), name=name)
            path = export_jdsl(result.package, Path(output))
            self.store.record_package(name, result.package.manifest.version, package_digest(result.package),
                                      status="built", path=str(path))
            self.write_log(
                f"Compiled {path}: replay={result.verification.replay_coverage:.2f}, "
                f"burden={result.compiled.stats.get('residual_decision_burden', 'n/a')}"
            )
            self.refresh_dashboard()
        except Exception as err:  # noqa: BLE001 - surface compile errors in the dashboard
            self.write_log(f"Compile failed: {err}")

    def on_unmount(self) -> None:
        if self.server:
            self.server.stop()


def run() -> None:
    """Run the interactive harness dashboard."""
    HarnessApp().run()


__all__ = ["HarnessApp", "run"]
