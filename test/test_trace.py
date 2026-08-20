"""Trace layer: canonical events, sinks, JSONL, blobs, redaction, replay, and the
runtime wiring (design §10, §11, §35 PR1/PR2/PR3/PR4)."""

from __future__ import annotations

from jdsl import (
    BlobStore,
    EventKind,
    ListTraceSink,
    Redactor,
    act,
    check,
    ref,
    root,
    seq,
    store,
)
from jdsl.trace import JsonlTraceSink, TraceEvent, read_events, segment_episodes, verify_chain
from jdsl.trace.sink import FanoutSink, SafeSink

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
