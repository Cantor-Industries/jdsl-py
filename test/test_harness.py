"""Harness layer: store, capture coordinator, tool gateway, and host adapters
(design §8, §28.1, §30, §46 hook fixture tests, §51 lineage report)."""

from __future__ import annotations

from jdsl import act, predict, ref, root, seq, store
from jdsl.trace import segment_episodes
from jdsl_harness.adapters import claude_code, gemini_cli, import_jsonl
from jdsl_harness.capture import CaptureCoordinator
from jdsl_harness.gateway import ToolGateway
from jdsl_harness.state import MappingEnvironment, Outcome
from jdsl_harness.store import HarnessStore

# -- store + capture coordinator ----------------------------------------------

def _teacher():
    def lookup(email: str): return {"id": "U17", "email": email}
    def list_orders(customer_id: str): return [{"id": "#W1", "status": "pending"}]
    return root("cancel").do(seq(
        store(act(lookup, email=ref("email")), "customer"),
        store(act(list_orders, customer_id=ref("customer_id")), "orders"),
        predict("request, orders -> selected_index", id="resolve"),
    ))


def test_store_records_and_reads_capture(tmp_path, fake_model):
    store_ = HarnessStore(tmp_path / "h")
    coord = CaptureCoordinator(store_)
    cap = coord.start(host="jdsl", adapter="runtime")
    _teacher().run(trace_sink=store_.sink(cap), model=fake_model("0"),
                   capture_id=cap, episode_id="ep_0",
                   email="a@b.com", customer_id="U17", request="cancel")
    coord.mark_outcome(cap, "ep_0", reward=1.0)
    coord.finish(cap)

    summary = coord.summary(cap)
    assert summary["events"] > 0
    assert summary["episodes"] == 1
    assert summary["fidelity"] in ("F2", "F3", "F4")

    caps = store_.list_captures()
    assert caps[0]["capture_id"] == cap
    assert caps[0]["status"] == "finished"


def test_lineage_report(tmp_path, fake_model):
    store_ = HarnessStore(tmp_path / "h")
    coord = CaptureCoordinator(store_)
    cap = coord.start()
    for i in range(3):
        _teacher().run(trace_sink=store_.sink(cap), model=fake_model("0"),
                       capture_id=cap, episode_id=f"ep_{i}",
                       email=f"c{i}@x.com", customer_id="U17", request="cancel")
    coord.finish(cap)
    report = coord.lineage_report(cap)
    assert len(report["episodes"]) == 3
    # customer.id -> list_orders.customer_id is a deterministic flow
    flows = {(f["from"], f["to"]) for ep in report["episodes"] for f in ep["flows"]}
    assert ("customer.id", "list_orders.customer_id") in flows
    assert any(c["type"] == "DATAFLOW" for c in report["deterministic_candidates"])
    assert any(c["type"] == "SEMANTIC" for c in report["residual_candidates"])


# -- tool gateway (Tier A, §8.1) ----------------------------------------------

def test_gateway_records_calls(tmp_path):
    from jdsl.trace import ListTraceSink
    sink = ListTraceSink()
    env = MappingEnvironment({"get_order": "retail.order.get"},
                             outcome_fn=lambda: Outcome(reward=1.0))
    gw = ToolGateway(sink, capture_id="cap", episode_id="ep", env=env)

    def get_order(order_id: str): return {"id": order_id, "status": "pending"}
    wrapped = gw.wrap(get_order, destructive=False)
    assert wrapped(order_id="#W1")["status"] == "pending"
    gw.record_outcome()

    ep = segment_episodes(sink.events)[0]
    calls = ep.tool_calls()
    assert calls[0].logical_id == "retail.order.get"
    assert calls[0].arguments == {"order_id": "#W1"}
    assert ep.succeeded() is True


def test_gateway_records_tool_error(tmp_path):
    from jdsl.trace import EventKind, ListTraceSink
    sink = ListTraceSink()
    gw = ToolGateway(sink, capture_id="c", episode_id="e")

    def flaky(x: str): return "Error: not_found"
    gw.wrap(flaky)(x="q")
    assert any(ev.kind == EventKind.TOOL_CALL_FAILED for ev in sink.events)


# -- host adapters (§46 hook fixtures) ----------------------------------------

def test_claude_hook_mapping():
    from jdsl.trace import EventKind
    pre = claude_code.to_events(
        {"hook_event_name": "PreToolUse", "session_id": "s1",
         "tool_name": "mcp__retail__get_order", "tool_input": {"order_id": "#W1"}},
        capture_id="cap")
    assert pre[0].kind == EventKind.TOOL_CALL_STARTED
    assert pre[0].episode_id == "s1"
    assert pre[0].payload["arguments"] == {"order_id": "#W1"}

    post = claude_code.to_events(
        {"hook_event_name": "PostToolUse", "session_id": "s1",
         "tool_name": "mcp__retail__get_order", "tool_response": {"status": "pending"}},
        capture_id="cap")
    assert post[0].kind == EventKind.TOOL_CALL_COMPLETED


def test_gemini_hook_mapping():
    from jdsl.trace import EventKind
    ev = gemini_cli.to_events(
        {"hook": "BeforeTool", "session_id": "g1", "tool_name": "get_order",
         "args": {"order_id": "#W1"}}, capture_id="cap")
    assert ev[0].kind == EventKind.TOOL_CALL_STARTED
    assert ev[0].source.host == "gemini-cli"


def test_import_records_roundtrips_through_compiler():
    from jdsl_harness.compiler import compile_behavior
    episodes_events = []
    for i in range(3):
        episodes_events += import_jsonl.import_records([
            {"tool": "lookup", "arguments": {"email": f"c{i}@x.com"}, "result": {"id": "U17"}},
            {"tool": "list_orders", "arguments": {"customer_id": "U17"}, "result": [{"id": "#W1"}]},
        ], capture_id="cap", episode_id=f"ep_{i}", outcome={"reward": 1.0})
    episodes = segment_episodes(episodes_events)
    result = compile_behavior(episodes, name="imported")
    # the customer id flows lookup.result.id -> list_orders.customer_id
    assert result.verification.structural_ok
    assert result.compiled.stats["exact_dataflow_refs"] >= 1
