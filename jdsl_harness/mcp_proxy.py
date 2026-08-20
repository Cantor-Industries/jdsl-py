"""Transparent MCP proxy — Tier-A capture for MCP-native tools (design §8.1.1,
§35 PR5).

Many modern tools already arrive through MCP. Rather than writing a wrapper per
tool, jdsl proxies an upstream MCP server: it discovers the upstream tools,
preserves their input/output schemas, exposes them namespaced to the host,
forwards calls, and records the full call + result to the trace store (§8.1.1).

The MCP SDK is an optional dependency (§36): this module defines the recording
logic in a transport-neutral way (`ProxiedTool`, `record_proxied_call`) that works
without `mcp`, and a `serve_proxy` entry point that lazily imports the SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jdsl.trace.events import EventKind, EventSource, TraceEvent
from jdsl.trace.sink import TraceSink


@dataclass
class ProxiedTool:
    """An upstream MCP tool the proxy exposes, with its preserved schema (§8.1.1)."""
    server: str
    name: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    @property
    def namespaced(self) -> str:
        """Host-visible name, namespaced by server to keep logical ids collision-free."""
        return f"mcp__{self.server}__{self.name}"

    @property
    def logical_id(self) -> str:
        return f"{self.server}.{self.name}"


def record_proxied_call(sink: TraceSink, tool: ProxiedTool, arguments: dict[str, Any],
                        *, capture_id: str, episode_id: str, result: Any = None,
                        error: Any = None) -> list[TraceEvent]:
    """Record one forwarded MCP call as canonical events (§8.1.1 items 4-6)."""
    src = EventSource(host="mcp-proxy", adapter="mcp-proxy")
    started = TraceEvent.new(EventKind.TOOL_CALL_STARTED, capture_id, episode_id, actor="model",
                             source=src, payload={
                                 "tool": {"host_name": tool.namespaced, "logical_id": tool.logical_id,
                                          "server": tool.server},
                                 "arguments": arguments})
    sink.emit(started)
    if error is not None:
        done = TraceEvent.new(EventKind.TOOL_CALL_FAILED, capture_id, episode_id, actor="tool",
                              source=src, parent_event_id=started.event_id,
                              payload={"tool": {"host_name": tool.namespaced}, "error": str(error)})
    else:
        done = TraceEvent.new(EventKind.TOOL_CALL_COMPLETED, capture_id, episode_id, actor="tool",
                              source=src, parent_event_id=started.event_id,
                              payload={"tool": {"host_name": tool.namespaced}, "result": result})
    sink.emit(done)
    return [started, done]


@dataclass
class MCPProxy:
    """Holds proxy configuration and the discovered upstream tool table. The actual
    stdio/HTTP transport is provided by `serve_proxy` (needs the `mcp` SDK)."""
    sink: TraceSink
    capture_id: str
    episode_id: str = "ep_proxy"
    tools: dict[str, ProxiedTool] = field(default_factory=dict)

    def register(self, tool: ProxiedTool) -> None:
        self.tools[tool.namespaced] = tool

    def toolset_event(self) -> TraceEvent:
        """Emit the exposed toolset for the compiler's tool-visibility mining (§42)."""
        event = TraceEvent.new(EventKind.TOOLSET_EXPOSED, self.capture_id, self.episode_id,
                               source=EventSource(host="mcp-proxy", adapter="mcp-proxy"),
                               payload={"tools": [{"host_name": t.namespaced, "logical_id": t.logical_id,
                                                   "description": t.description}
                                                  for t in self.tools.values()]})
        return self.sink.emit(event)

    def record(self, namespaced: str, arguments: dict[str, Any], *, result: Any = None,
               error: Any = None) -> list[TraceEvent]:
        tool = self.tools.get(namespaced) or ProxiedTool(server="unknown", name=namespaced)
        return record_proxied_call(self.sink, tool, arguments, capture_id=self.capture_id,
                                   episode_id=self.episode_id, result=result, error=error)


def serve_proxy(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover - needs mcp SDK
    """Run the live MCP proxy transport. Requires the `mcp` package."""
    try:
        import mcp  # type: ignore  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "the MCP proxy transport needs the 'mcp' package: pip install 'jdsl[harness]'") from e
    raise NotImplementedError(
        "live MCP transport wiring is host-specific; use MCPProxy.record(...) from your "
        "MCP middleware, or the IngestServer /ingest endpoint, to record proxied calls.")


__all__ = ["ProxiedTool", "record_proxied_call", "MCPProxy", "serve_proxy"]
