"""Progress and privacy-conscious trace display for a skill run."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
import json

from textual.widgets import ProgressBar, RichLog, Static


class RunTraceUpdate(Message):
    """A sanitized event summary forwarded from the run worker."""

    def __init__(self, kind: str, node_id: str | None, status: str | None, tool_name: str | None = None) -> None:
        super().__init__()
        self.kind = kind
        self.node_id = node_id
        self.status = status
        self.tool_name = tool_name


class RunPanel(Vertical):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.dry_run = False
        self.intended_calls: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static("RUN TRACE", classes="panel-header panel-title")
        yield ProgressBar(total=1, show_eta=False, id="run-progress")
        yield RichLog(id="run-log", markup=False, wrap=True, max_lines=500)

    def begin(self, total: int, *, dry_run: bool = False) -> None:
        self.styles.display = "block"
        self.dry_run = dry_run
        self.intended_calls.clear()
        self.query_one("#run-log", RichLog).clear()
        self.query_one("#run-progress", ProgressBar).update(total=max(1, total), progress=0)
        label = "Dry run started; tools will not execute." if dry_run else "Run started."
        self.query_one("#run-log", RichLog).write(label)

    def add_trace(self, update: RunTraceUpdate) -> None:
        log = self.query_one("#run-log", RichLog)
        label = update.node_id or update.kind
        if self.dry_run and update.kind == "tool.call.started":
            tool_name = update.tool_name or label
            self.intended_calls.append(tool_name)
            log.write(f"Would call {tool_name} from {label}.")
            return
        if update.status:
            log.write(f"{update.kind}: {label} [{update.status}]")
            if update.kind == "node.exit":
                self.query_one("#run-progress", ProgressBar).advance(1)
        elif update.kind.startswith("tool."):
            log.write(f"{update.kind}: {label}")
        else:
            log.write(f"{update.kind}: {label}")

    def finish(self, message: str) -> None:
        self.query_one("#run-log", RichLog).write(message)

    def show_blackboard(self, blackboard: dict) -> None:
        self.query_one("#run-log", RichLog).write("Final blackboard (secret values redacted):")
        self.query_one("#run-log", RichLog).write(json.dumps(blackboard, indent=2, sort_keys=True, default=str))


__all__ = ["RunPanel", "RunTraceUpdate"]
