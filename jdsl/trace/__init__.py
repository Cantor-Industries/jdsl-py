"""jdsl canonical trace layer (design §10, §11, §35 PR1/PR4).

A host-neutral, append-only, hash-chained event model plus the sinks, storage,
redaction, and replay helpers built on it. The runtime (`RunContext.trace_sink`)
and every capture adapter emit into this one model.
"""

from jdsl.trace.blobs import BlobStore
from jdsl.trace.events import SCHEMA_VERSION, EventKind, EventSource, TraceEvent
from jdsl.trace.jsonl import JsonlTraceSink, iter_events, read_events, verify_chain
from jdsl.trace.redaction import Redactor, with_paths
from jdsl.trace.replay import Episode, ToolInvocation, segment_episodes
from jdsl.trace.sink import (
    FanoutSink,
    ListTraceSink,
    NullTraceSink,
    SafeSink,
    TraceSink,
)

__all__ = [
    "SCHEMA_VERSION",
    "EventKind",
    "EventSource",
    "TraceEvent",
    "TraceSink",
    "NullTraceSink",
    "ListTraceSink",
    "SafeSink",
    "FanoutSink",
    "JsonlTraceSink",
    "read_events",
    "iter_events",
    "verify_chain",
    "BlobStore",
    "Redactor",
    "with_paths",
    "Episode",
    "ToolInvocation",
    "segment_episodes",
]
