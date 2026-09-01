"""Trace layer: canonical events, sinks, JSONL, blobs, redaction, replay, and the
runtime wiring (design §10, §11, §35 PR1/PR2/PR3/PR4)."""

from __future__ import annotations

import pytest

from jdsl import (
    BlobStore,
    EventKind,
    ListTraceSink,
    Redactor,
    act,
    check,
    predict,
    ref,
    root,
    seq,
    store,
)
from jdsl.trace import JsonlTraceSink, TraceEvent, read_events, segment_episodes, verify_chain
from jdsl.trace.sink import FanoutSink, SafeSink
from jdsl.tree import Predict

# -- fixtures -----------------------------------------------------------------

def _customer_lookup(email: str) -> dict:
    return {"id": "U17", "email": email}


def _list_orders(customer_id: str) -> list[dict]:
    return [{"id": "#W1", "status": "pending"}, {"id": "#W2", "status": "shipped"}]


def _skill():
    return root("cancel").do(seq(
        store(act(_customer_lookup, email=ref("email")), "customer"),
        store(act(_list_orders, customer_id=ref("customer_id")), "orders"),
        check("orders_len", 2),
    ))


# -- events -------------------------------------------------------------------

def test_event_hash_and_roundtrip():
    e = TraceEvent.new(EventKind.USER_MESSAGE, "cap_1", "ep_1", payload={"text": "hi"})
    e.chain(None)
    assert e.verify_hash()
    again = TraceEvent.from_dict(e.to_dict())
    assert again.verify_hash()
    assert again.event_id == e.event_id
    assert again.source.host == "jdsl"


def test_chain_links_and_detects_tamper():
    sink = ListTraceSink()
    for i in range(3):
        sink.emit(TraceEvent.new(EventKind.ANNOTATION, "cap", "ep", payload={"i": i}))
    assert verify_chain(sink.events) == []
    # tamper with a middle event's payload without rehashing -> chain breaks
    sink.events[1].payload["i"] = 999
    assert verify_chain(sink.events) != []


def test_sequence_is_per_episode():
    sink = ListTraceSink()
    sink.emit(TraceEvent.new(EventKind.ANNOTATION, "cap", "ep_a"))
    sink.emit(TraceEvent.new(EventKind.ANNOTATION, "cap", "ep_b"))
    sink.emit(TraceEvent.new(EventKind.ANNOTATION, "cap", "ep_a"))
    seqs_a = [e.sequence for e in sink.episode("ep_a")]
    assert seqs_a == [0, 1]
    assert sink.episode("ep_b")[0].sequence == 0


# -- runtime wiring (PR1) -----------------------------------------------------

def test_run_emits_node_and_blackboard_events():
    sink = ListTraceSink()
    _skill().run(trace_sink=sink, email="a@b.com", customer_id="U17", orders_len=2)
    kinds = [e.kind for e in sink.events]
    assert EventKind.EPISODE_STARTED in kinds
    assert EventKind.EPISODE_FINISHED in kinds
    assert kinds.count(EventKind.NODE_ENTER) == kinds.count(EventKind.NODE_EXIT)
    writes = [e for e in sink.events if e.kind == EventKind.BLACKBOARD_WRITE]
    written_keys = {e.payload["key"] for e in writes}
    assert {"customer", "orders"} <= written_keys
    assert verify_chain(sink.events) == []


def test_untraced_run_is_unchanged():
    ctx = _skill().run(email="a@b.com", customer_id="U17", orders_len=2)
    assert ctx.blackboard["customer"]["id"] == "U17"
    assert not ctx.tracing


def test_node_exit_carries_status():
    sink = ListTraceSink()
    _skill().run(trace_sink=sink, email="a@b.com", customer_id="U17", orders_len=2)
    exits = [e for e in sink.events if e.kind == EventKind.NODE_EXIT]
    assert all("status" in e.payload for e in exits)
    assert any(e.payload["status"] == "success" for e in exits)


# -- stable node ids (PR3) ----------------------------------------------------

def test_author_node_id_appears_in_trace():
    sink = ListTraceSink()
    skill = root("x").do(seq(check("k", 1, id="mycheck"), id="myseq"))
    skill.run(trace_sink=sink, k=1)
    ids = {e.payload.get("node_id") for e in sink.events if e.kind == EventKind.NODE_ENTER}
    assert "mycheck" in ids
    assert "myseq" in ids


def test_runtime_ids_assigned_when_no_author_id():
    sink = ListTraceSink()
    _skill().run(trace_sink=sink, email="a@b.com", customer_id="U17", orders_len=2)
    ids = [e.payload.get("node_id") for e in sink.events if e.kind == EventKind.NODE_ENTER]
    assert all(i for i in ids)  # every node got some id (author or path-derived)


# -- storage (PR4) ------------------------------------------------------------

def test_jsonl_roundtrip(tmp_path):
    path = tmp_path / "trace.jsonl"
    sink = JsonlTraceSink(path)
    _skill().run(trace_sink=sink, email="a@b.com", customer_id="U17", orders_len=2)
    loaded = read_events(path)
    assert verify_chain(loaded) == []
    episodes = segment_episodes(loaded)
    assert len(episodes) == 1
    assert episodes[0].final_blackboard()["customer"]["id"] == "U17"


def test_blob_store_dedupes(tmp_path):
    store_ = BlobStore(tmp_path / "blobs")
    r1 = store_.put_json({"a": 1, "b": 2})
    r2 = store_.put_json({"b": 2, "a": 1})  # same content, different order
    assert r1 == r2
    assert store_.get_json(r1) == {"a": 1, "b": 2}


def test_fanout_and_safe_sink(tmp_path):
    mem = ListTraceSink()

    class Broken:
        def emit(self, e):
            raise RuntimeError("boom")

    fan = FanoutSink(mem, SafeSink(Broken(), warn=False))
    _skill().run(trace_sink=fan, email="a@b.com", customer_id="U17", orders_len=2)
    assert len(mem.events) > 0  # run completed despite the broken secondary sink


# -- redaction (§31.2) --------------------------------------------------------

def test_redactor_strips_secrets_and_paths():
    r = Redactor(json_paths=("customer.email",))
    out = r.redact({
        "api_key": "sk-abcdefghijklmnop1234",
        "customer": {"email": "person@example.com", "id": "U17"},
        "note": "token sk-ant-abcdefghij1234567890 here",
    })
    assert out["api_key"] == "«redacted»"
    assert out["customer"]["email"] == "«redacted»"
    assert out["customer"]["id"] == "U17"
    assert "«redacted»" in out["note"]


# -- replay views -------------------------------------------------------------

def test_tool_calls_reconstructed_from_events():
    sink = ListTraceSink()
    _skill().run(trace_sink=sink, email="a@b.com", customer_id="U17", orders_len=2)
    ep = segment_episodes(sink.events)[0]
    states = ep.blackboard_states()
    assert states[-1][1]["customer"]["id"] == "U17"


# -- predict model telemetry --------------------------------------------------

def test_predict_emits_model_request_and_response(fake_model):
    sink = ListTraceSink()
    node = Predict(inputs=("request", "orders"), outputs=("selected_index",),
                   instructions="Pick the matching order index.",
                   output_schemas={"selected_index": {"type": "integer", "minimum": 0}},
                   signature_id="resolve_target_order")
    node.node_id = "resolve_target"
    skill = root("selector").model("deepseek-chat").do(seq(node))
    ctx = skill.run(trace_sink=sink, model=fake_model("1"), request="blue shoes",
                    orders=[{"id": "#W1", "summary": "red shirt"}, {"id": "#W2", "summary": "blue shoes"}])

    assert ctx.blackboard["selected_index"] == 1
    requests = [e for e in sink.events if e.kind == EventKind.MODEL_REQUESTED]
    responses = [e for e in sink.events if e.kind == EventKind.MODEL_RESPONDED]
    assert len(requests) == 1
    assert len(responses) == 1
    assert requests[0].payload["node_id"] == "resolve_target"
    assert requests[0].payload["signature_id"] == "resolve_target_order"
    assert requests[0].payload["input_fields"] == ["request", "orders"]
    assert requests[0].payload["output_fields"] == ["selected_index"]
    assert requests[0].payload["model_id"] == "deepseek-chat"
    assert responses[0].parent_event_id == requests[0].event_id
    assert responses[0].payload["parsed_output"] == 1
    assert responses[0].payload["status"] == "success"
    assert isinstance(responses[0].payload["elapsed_ms"], float)


def test_predict_model_call_failure_is_traced():
    class BrokenModel:
        def generate(self, **kwargs):
            raise RuntimeError("model unavailable")

    sink = ListTraceSink()
    skill = root("broken").model("deepseek-chat").do(seq(predict("q -> answer", id="ask")))
    with pytest.raises(RuntimeError, match="model unavailable"):
        skill.run(trace_sink=sink, model=BrokenModel(), q="?")

    responses = [e for e in sink.events if e.kind == EventKind.MODEL_RESPONDED]
    assert len(responses) == 1
    assert responses[0].payload["node_id"] == "ask"
    assert responses[0].payload["status"] == "failure"
    assert "model unavailable" in responses[0].payload["error"]


def test_predict_trace_sink_failure_uses_existing_safe_sink_policy(fake_model):
    mem = ListTraceSink()

    class Broken:
        def emit(self, event):
            raise RuntimeError("sink down")

    sink = FanoutSink(mem, SafeSink(Broken(), warn=False))
    ctx = root("safe").model("deepseek-chat").do(seq(predict("q -> answer"))).run(
        trace_sink=sink, model=fake_model("ok"), q="?")
    assert ctx.blackboard["answer"] == "ok"
    assert [e.kind for e in mem.events].count(EventKind.MODEL_REQUESTED) == 1
    assert [e.kind for e in mem.events].count(EventKind.MODEL_RESPONDED) == 1


def test_rdb_zero_package_emits_no_model_events():
    import importlib.util

    spec = importlib.util.spec_from_file_location("retail_tools", "examples/harness/retail_tools.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    from jdsl.package import load_package

    sink = ListTraceSink()
    pkg = load_package("examples/harness/retail.jdsl")
    ctx = pkg.as_root(mod.TOOLS).run(trace_sink=sink, email="ada@example.com")
    assert ctx.blackboard["mcp_retail_get_order_out_3"]["id"] == "O_ada_1"
    assert all(e.kind not in (EventKind.MODEL_REQUESTED, EventKind.MODEL_RESPONDED) for e in sink.events)
