"""Harness daemon: local ingest data plane + MCP control plane (design §7, §28,
§35 PR6).

The architectural split of §7 lives here. The *data plane* is a fast local HTTP
loopback endpoint that host hooks POST events to and returns immediately (§7.2) —
never a slow remote request on every tool event. The *control plane* (§7.1, §28)
is a small, stable set of operations (`jdsl.capture.*`, `jdsl.compile`, …) exposed
as an MCP server when the MCP SDK is available, and always available in-process via
`CaptureCoordinator`.

MCP is optional: importing this module never requires the `mcp` package. If it is
absent, `build_mcp_server` raises a clear error and the HTTP ingest server still
runs.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from jdsl.trace.events import TraceEvent
from jdsl_harness.adapters import claude_code, gemini_cli, opencode
from jdsl_harness.adapters.correlation import ToolCallCorrelator
from jdsl_harness.capture import CaptureCoordinator
from jdsl_harness.store import HarnessStore


class IngestServer:
    """Loopback HTTP ingest for host hooks and adapters (§7.2 telemetry plane).

    Endpoints:
        POST /ingest             body: a canonical TraceEvent dict
        POST /hook/claude?cap=…  body: a Claude Code hook payload
        POST /hook/gemini?cap=…  body: a Gemini CLI hook payload
        POST /hook/opencode?cap=… body: a jdsl OpenCode hook envelope
        GET  /captures           list captures
        GET  /capture/<id>/summary
    The hook itself fails open for observation (§7.2): a bad request never 500s the
    agent — it returns a 200 with an error note so the host loop keeps moving."""

    def __init__(self, store: HarnessStore, *, host: str = "127.0.0.1", port: int = 8848) -> None:
        self.store = store
        self.coord = CaptureCoordinator(store)
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._claude_correlator = ToolCallCorrelator()
        self._gemini_correlator = ToolCallCorrelator()
        self._opencode_correlator = ToolCallCorrelator()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # keep the agent's terminal quiet
                pass

            def _json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(length) if length else b"{}"
                return json.loads(raw or b"{}")

            def _reply(self, code: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _cap(self) -> str:
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                return (q.get("cap") or ["cap_ingest"])[0]

            def do_POST(self) -> None:  # noqa: N802
                try:
                    payload = self._json()
                    path = self.path.split("?", 1)[0]
                    if path == "/ingest":
                        event = TraceEvent.from_dict(payload)
                        server.store.ingest(event)
                    elif path == "/hook/claude":
                        for e in claude_code.to_events(payload, capture_id=self._cap(),
                                                       correlator=server._claude_correlator):
                            server.store.ingest(e)
                    elif path == "/hook/gemini":
                        for e in gemini_cli.to_events(payload, capture_id=self._cap(),
                                                      correlator=server._gemini_correlator):
                            server.store.ingest(e)
                    elif path == "/hook/opencode":
                        for e in opencode.to_events(payload, capture_id=self._cap(),
                                                    correlator=server._opencode_correlator):
                            server.store.ingest(e)
                    else:
                        return self._reply(404, {"error": "unknown endpoint"})
                    self._reply(200, {"ok": True})
                except Exception as err:  # noqa: BLE001 — fail open (§7.2)
                    self._reply(200, {"ok": False, "error": str(err)})

            def do_GET(self) -> None:  # noqa: N802
                path = self.path.split("?", 1)[0]
                if path == "/captures":
                    return self._reply(200, {"captures": server.store.list_captures()})
                if path.startswith("/capture/") and path.endswith("/summary"):
                    cid = path[len("/capture/"):-len("/summary")]
                    return self._reply(200, server.coord.summary(cid))
                self._reply(404, {"error": "unknown endpoint"})

        return Handler

    def start(self) -> IngestServer:
        self._httpd = ThreadingHTTPServer((self.host, self.port), self._handler())
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def __enter__(self) -> IngestServer:
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()


# -- MCP control plane (optional) --------------------------------------------

def _mcp_server(name: str) -> Any:
    """Instantiate a decorator-style MCP server across SDK versions: `MCPServer`
    on mcp >= 2.0 (which renamed it from `FastMCP`), `FastMCP` on mcp 1.x. Both
    expose the same `.tool()` decorator and `.run()`. Raises a clear error when the
    MCP SDK is absent, keeping the core harness free of a hard MCP dependency (§36)."""
    try:
        from mcp.server import MCPServer  # type: ignore  # mcp >= 2.0
        return MCPServer(name)
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore  # mcp 1.x
        return FastMCP(name)
    except ImportError as e:  # pragma: no cover - exercised only with mcp installed
        raise RuntimeError(
            "the MCP control plane needs the 'mcp' package: uv sync --extra harness") from e


def build_mcp_server(store: HarnessStore, name: str = "jdsl-harness") -> Any:
    """Build an MCP server exposing the control tools (§28.1). Requires the `mcp`
    package; raises a clear error if it is not installed. Kept import-optional so
    the core harness never depends on the MCP SDK (§36)."""
    coord = CaptureCoordinator(store)
    mcp = _mcp_server(name)

    @mcp.tool()
    def jdsl_capture_start(host: str = "jdsl", adapter: str = "runtime", note: str = "") -> dict:
        return {"capture_id": coord.start(host=host, adapter=adapter, note=note)}

    @mcp.tool()
    def jdsl_capture_finish(capture_id: str) -> dict:
        coord.finish(capture_id)
        return {"ok": True}

    @mcp.tool()
    def jdsl_capture_mark_outcome(capture_id: str, episode_id: str, reward: float | None = None,
                                  verdict: str | None = None) -> dict:
        coord.mark_outcome(capture_id, episode_id, reward=reward, verdict=verdict)
        return {"ok": True}

    @mcp.tool()
    def jdsl_capture_summary(capture_id: str) -> dict:
        return coord.summary(capture_id)

    @mcp.tool()
    def jdsl_inspect(capture_id: str) -> dict:
        return coord.lineage_report(capture_id)

    @mcp.tool()
    def jdsl_compile(capture_id: str, name: str = "behavior") -> dict:
        from jdsl_harness.compiler import compile_behavior
        result = compile_behavior(store.capture_episodes(capture_id), name=name)
        return result.report()

    return mcp


__all__ = ["IngestServer", "build_mcp_server"]
