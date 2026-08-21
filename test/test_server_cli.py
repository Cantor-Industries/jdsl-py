"""Local ingest server (§7.2 data plane), MCP proxy recording (§8.1.1), and the
CLI package/compile commands (§37)."""

from __future__ import annotations

import json
import urllib.request

from typer.testing import CliRunner

from jdsl.cli import app
from jdsl.trace import ListTraceSink, segment_episodes
from jdsl.trace.events import EventKind, TraceEvent
from jdsl_harness.mcp_proxy import MCPProxy, ProxiedTool
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


# -- CLI ----------------------------------------------------------------------

def _build_pkg(path):
    from jdsl.package import export_jdslpkg
    from test.test_package import _pkg
    return export_jdslpkg(_pkg(), path)


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
    assert (tmp_path / "out.jdslpkg").exists()
    report = json.loads(r.stdout[r.stdout.index("{"):r.stdout.rindex("}") + 1])
    assert report["verification"]["status"] == "passed"
