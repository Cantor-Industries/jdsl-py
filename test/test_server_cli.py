"""Local ingest server (§7.2 data plane), MCP proxy recording (§8.1.1), and the
CLI package/compile commands (§37)."""

from __future__ import annotations

import json
import sys
import urllib.request

from typer.testing import CliRunner

from jdsl.cli import app
from jdsl.trace import ListTraceSink, segment_episodes
from jdsl.trace.events import EventKind, TraceEvent
from jdsl_harness.mcp_proxy import MCPProxy, ProxiedTool, StdioUpstream, build_stdio_proxy_server
from jdsl_harness.server import IngestServer
from jdsl_harness.store import HarnessStore

runner = CliRunner()


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


# -- ingest server ------------------------------------------------------------

def test_ingest_server_records_canonical_and_hooks(tmp_path):
    store = HarnessStore(tmp_path / "h")
    with IngestServer(store, port=0) as server:
        # a raw canonical event
        ev = TraceEvent.new(EventKind.USER_MESSAGE, "cap_x", "ep_1", payload={"text": "hi"})
        assert _post(server.url + "/ingest", ev.to_dict())["ok"]
        # a Claude hook payload for the same capture
        assert _post(server.url + "/hook/claude?cap=cap_x",
                     {"hook_event_name": "PreToolUse", "session_id": "ep_1",
                      "tool_name": "get_order", "tool_input": {"order_id": "#W1"}})["ok"]
        summary = _get(server.url + "/capture/cap_x/summary")
        caps = _get(server.url + "/captures")

    assert summary["events"] >= 2
    assert any(c["capture_id"] == "cap_x" for c in caps["captures"])


def test_ingest_server_records_opencode_hook_with_correlation(tmp_path):
    store = HarnessStore(tmp_path / "h")
    with IngestServer(store, port=0) as server:
        assert _post(server.url + "/hook/opencode?cap=cap_open",
                     {"schema": "jdsl.opencode-hook.v1", "hook": "tool.execute.before",
                      "session_id": "ses_1", "call_id": "call_1", "tool": "read",
                      "args": {"filePath": "README.md"}})["ok"]
        assert _post(server.url + "/hook/opencode?cap=cap_open",
                     {"schema": "jdsl.opencode-hook.v1", "hook": "tool.execute.after",
                      "session_id": "ses_1", "call_id": "call_1", "tool": "read",
                      "result": "hello"})["ok"]

    events = store.capture_events("cap_open")
    start = next(e for e in events if e.kind == EventKind.TOOL_CALL_STARTED)
    done = next(e for e in events if e.kind == EventKind.TOOL_CALL_COMPLETED)
    assert done.parent_event_id == start.event_id
    assert done.payload["host_call_id"] == "call_1"


def test_build_mcp_control_plane_across_sdk_versions(tmp_path):
    """The §28 control plane must build against whatever MCP SDK is installed —
    mcp 2.x (`MCPServer`) or 1.x (`FastMCP`). Skips when the SDK is absent."""
    import asyncio

    import pytest
    pytest.importorskip("mcp")
    from jdsl_harness.server import build_mcp_server

    srv = build_mcp_server(HarnessStore(tmp_path / "h"))
    tools = asyncio.new_event_loop().run_until_complete(srv.list_tools())
    names = {t.name for t in tools}
    assert {"jdsl_capture_start", "jdsl_compile", "jdsl_inspect"} <= names


def test_ingest_fails_open_on_bad_payload(tmp_path):
    store = HarnessStore(tmp_path / "h")
    with IngestServer(store, port=0) as server:
        # malformed event: server returns 200 with ok=False (never 500), §7.2
        resp = _post(server.url + "/ingest", {"kind": None})
    assert resp["ok"] is False


# -- MCP proxy recording ------------------------------------------------------

def test_mcp_proxy_records_namespaced_calls():
    sink = ListTraceSink()
    proxy = MCPProxy(sink=sink, capture_id="cap", episode_id="ep")
    proxy.register(ProxiedTool(server="retail", name="get_order",
                               input_schema={"type": "object"}))
    proxy.toolset_event()
    proxy.record("mcp__retail__get_order", {"order_id": "#W1"}, result={"status": "pending"})

    ep = segment_episodes(sink.events)[0]
    call = ep.tool_calls()[0]
    assert call.logical_id == "retail.get_order"
    assert call.arguments == {"order_id": "#W1"}


def test_stdio_mcp_proxy_discovers_calls_and_records(tmp_path):
    import anyio
    from mcp import types

    server_script = tmp_path / "fake_mcp.py"
    server_script.write_text(
        """
from mcp.server import MCPServer

mcp = MCPServer("fake-retail")

@mcp.tool()
def lookup(email: str) -> dict:
    return {"id": "U17", "email": email}

if __name__ == "__main__":
    import anyio
    anyio.run(mcp.run_stdio_async)
""".lstrip(),
        encoding="utf-8",
    )

    sink = ListTraceSink()
    upstream = StdioUpstream(server="retail", command=sys.executable, args=[str(server_script)])
    proxy = build_stdio_proxy_server(upstream, sink, capture_id="cap", episode_id="ep")

    async def exercise():
        tools = await proxy._jdsl_on_list_tools(None, None)
        assert tools.tools[0].name == "mcp__retail__lookup"
        assert tools.tools[0].input_schema["properties"]["email"]["type"] == "string"
        result = await proxy._jdsl_on_call_tool(
            None,
            types.CallToolRequestParams(name="mcp__retail__lookup", arguments={"email": "a@b.com"}),
        )
        assert '"id": "U17"' in result.content[0].text

    anyio.run(exercise)

    ep = segment_episodes(sink.events)[0]
    call = ep.tool_calls()[0]
    assert call.logical_id == "retail.lookup"
    assert call.arguments == {"email": "a@b.com"}
    assert call.result == {"id": "U17", "email": "a@b.com"}


# -- CLI ----------------------------------------------------------------------

def _build_pkg(path):
    from jdsl.package import export_jdsl
    from test.test_package import _pkg
    return export_jdsl(_pkg(), path)


def test_cli_package_inspect_and_verify(tmp_path):
    pkg_path = _build_pkg(tmp_path / "retail")
    r = runner.invoke(app, ["package", "inspect", str(pkg_path)])
    assert r.exit_code == 0
    assert "retail-cancellation" in r.stdout

    r = runner.invoke(app, ["package", "verify", str(pkg_path)])
    assert r.exit_code == 0
    assert "valid" in r.stdout


def test_cli_capture_import_and_compile(tmp_path, monkeypatch):
    """Tier-C import from the CLI: a foreign JSONL log becomes a compilable
    capture (§8.3)."""
    monkeypatch.setenv("JDSL_HARNESS_HOME", str(tmp_path / "store"))
    log = tmp_path / "foreign.jsonl"
    log.write_text(
        "\n".join(json.dumps({
            "episode_id": f"imp_{i}",
            "steps": [
                {"tool": "lookup", "args": {"email": f"u{i}@x.com"}, "result": {"id": f"c{i}"}},
                {"tool": "list_orders", "args": {"customer_id": f"c{i}"},
                 "result": [{"id": f"o{i}0"}, {"id": f"o{i}1"}]},
                {"tool": "get_order", "args": {"order_id": f"o{i}1"},
                 "result": {"id": f"o{i}1", "status": "open"}},
            ],
            "outcome": {"reward": 1.0},
        }) for i in range(3)),
        encoding="utf-8")

    r = runner.invoke(app, ["capture", "import", str(log), "--capture", "cap_imp"])
    assert r.exit_code == 0, r.output
    assert "imported" in r.stdout

    r = runner.invoke(app, ["compile", "cap_imp", "--name", "support"])
    assert r.exit_code == 0, r.output
    report = json.loads(r.stdout[r.stdout.index("{"):r.stdout.rindex("}") + 1])
    assert report["verification"]["status"] == "passed"
    # email varies across imported episodes with no dataflow -> a declared input
    assert "email" in report["stats"]["inputs"]


def test_cli_compile(tmp_path, monkeypatch):
    # point the harness store at a temp dir and seed a capture via the store
    monkeypatch.setenv("JDSL_HARNESS_HOME", str(tmp_path / "store"))
    from test.conftest import FakeModel
    from test.test_harness import _teacher
    store = HarnessStore(tmp_path / "store")
    from jdsl_harness.capture import CaptureCoordinator
    coord = CaptureCoordinator(store)
    cap = coord.start()
    for i in range(3):
        _teacher().run(trace_sink=store.sink(cap), model=FakeModel("0"),
                       capture_id=cap, episode_id=f"ep_{i}",
                       email=f"c{i}@x.com", customer_id="U17", request="cancel")
        coord.mark_outcome(cap, f"ep_{i}", reward=1.0)
    coord.finish(cap)

    r = runner.invoke(app, ["compile", cap, "--name", "retail", "--out", str(tmp_path / "out")])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "out.jdsl").exists()
    report = json.loads(r.stdout[r.stdout.index("{"):r.stdout.rindex("}") + 1])
    assert report["verification"]["status"] == "passed"
