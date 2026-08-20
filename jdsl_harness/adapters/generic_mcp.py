"""Generic MCP-host adapter (design §8.2 "Hosts without global tool hooks", §29.3).

For a host that speaks MCP but exposes no global tool hooks, jdsl sees only the
tool calls routed through its own gateway/proxy. This adapter maps an MCP
tools/call request+result pair into canonical events and records that capture
fidelity is limited to jdsl-routed tools — it never claims full host visibility
(§8.2 "Do not claim full capture when the plugin only sees jdsl MCP calls").
"""

from __future__ import annotations

from typing import Any

from jdsl.trace.events import EventKind, EventSource, TraceEvent

HOST = "generic-mcp"
ADAPTER = "mcp-routed"


def call_events(*, capture_id: str, episode_id: str, server: str, tool: str,
                arguments: dict[str, Any], result: Any = None, error: Any = None,
                logical_id: str | None = None) -> list[TraceEvent]:
    """One MCP tool call → started + completed/failed. `server` namespaces the tool
    so logical ids stay collision-free across MCP servers (§44.3)."""
    src = EventSource(host=HOST, adapter=ADAPTER)
    host_name = f"mcp__{server}__{tool}"
    started = TraceEvent.new(EventKind.TOOL_CALL_STARTED, capture_id, episode_id, actor="model",
                             source=src, payload={
                                 "tool": {"host_name": host_name, "logical_id": logical_id,
                                          "server": server}, "arguments": arguments})
    if error is not None:
        done = TraceEvent.new(EventKind.TOOL_CALL_FAILED, capture_id, episode_id, actor="tool",
                              source=src, parent_event_id=started.event_id,
                              payload={"tool": {"host_name": host_name}, "error": str(error)})
    else:
        done = TraceEvent.new(EventKind.TOOL_CALL_COMPLETED, capture_id, episode_id, actor="tool",
                              source=src, parent_event_id=started.event_id,
                              payload={"tool": {"host_name": host_name}, "result": result})
    return [started, done]


__all__ = ["call_events", "HOST", "ADAPTER"]
