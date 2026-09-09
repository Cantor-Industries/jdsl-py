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

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
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
                        error: Any = None, host_call_id: str | None = None) -> list[TraceEvent]:
    """Record one forwarded MCP call as canonical events (§8.1.1 items 4-6)."""
    src = EventSource(host="mcp-proxy", adapter="mcp-proxy")
    start_payload = {
        "tool": {"host_name": tool.namespaced, "logical_id": tool.logical_id, "server": tool.server},
        "arguments": arguments,
    }
    if host_call_id is not None:
        start_payload["host_call_id"] = host_call_id
        start_payload["correlation"] = {"method": "host_call_id", "fidelity": "exact"}
    started = TraceEvent.new(EventKind.TOOL_CALL_STARTED, capture_id, episode_id, actor="model",
                             source=src, payload=start_payload)
    sink.emit(started)
    if error is not None:
        payload = {"tool": {"host_name": tool.namespaced}, "error": str(error)}
        if host_call_id is not None:
            payload["host_call_id"] = host_call_id
        done = TraceEvent.new(EventKind.TOOL_CALL_FAILED, capture_id, episode_id, actor="tool",
                              source=src, parent_event_id=started.event_id,
                              payload=payload)
    else:
        payload = {"tool": {"host_name": tool.namespaced}, "result": result}
        if host_call_id is not None:
            payload["host_call_id"] = host_call_id
        done = TraceEvent.new(EventKind.TOOL_CALL_COMPLETED, capture_id, episode_id, actor="tool",
                              source=src, parent_event_id=started.event_id,
                              payload=payload)
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
               error: Any = None, host_call_id: str | None = None) -> list[TraceEvent]:
        tool = self.tools.get(namespaced) or ProxiedTool(server="unknown", name=namespaced)
        return record_proxied_call(self.sink, tool, arguments, capture_id=self.capture_id,
                                   episode_id=self.episode_id, result=result, error=error,
                                   host_call_id=host_call_id)


@dataclass
class StdioUpstream:
    """One upstream MCP server reached over stdio."""
    server: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | Path | None = None


def build_stdio_proxy_server(upstream: StdioUpstream | dict[str, Any], sink: TraceSink, *,
                             capture_id: str, episode_id: str = "ep_proxy",
                             name: str = "jdsl-mcp-proxy") -> Any:
    """Build a low-level MCP stdio proxy server for one upstream.

    The server discovers upstream tools, exposes namespaced copies with preserved
    JSON schemas, forwards calls to the upstream tool name, and records canonical
    tool-call events.
    """
    try:
        from mcp import types
        from mcp.server.lowlevel import Server
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise RuntimeError("the MCP proxy transport needs the 'mcp' package: uv sync --extra harness") from e

    config = _upstream(upstream)
    proxy = MCPProxy(sink=sink, capture_id=capture_id, episode_id=episode_id)

    async def ensure_tools() -> None:
        if proxy.tools:
            return
        tools = await discover_stdio_tools(config)
        for tool in tools:
            proxy.register(ProxiedTool(
                server=config.server,
                name=tool.name,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema or {},
                description=tool.description or "",
            ))
        proxy.toolset_event()

    async def on_list_tools(_ctx: Any, _params: Any) -> Any:
        await ensure_tools()
        return types.ListToolsResult(tools=[_as_mcp_tool(t) for t in proxy.tools.values()])

    async def on_call_tool(_ctx: Any, params: Any) -> Any:
        await ensure_tools()
        tool = proxy.tools.get(params.name)
        if tool is None:
            raise ValueError(f"unknown proxied tool {params.name!r}")
        arguments = params.arguments or {}
        result = await call_stdio_tool(config, tool.name, arguments)
        payload = _dump_mcp_result(result)
        if getattr(result, "is_error", False):
            proxy.record(tool.namespaced, arguments, error=payload)
        else:
            proxy.record(tool.namespaced, arguments, result=payload)
        return result

    server = Server(name, on_list_tools=on_list_tools, on_call_tool=on_call_tool)
    server._jdsl_on_list_tools = on_list_tools  # type: ignore[attr-defined]
    server._jdsl_on_call_tool = on_call_tool  # type: ignore[attr-defined]
    return server


async def discover_stdio_tools(upstream: StdioUpstream | dict[str, Any]) -> list[Any]:
    """Discover tools from one stdio upstream using the installed MCP SDK."""
    config = _upstream(upstream)
    async with _stdio_session(config) as session:
        result = await session.list_tools()
        return list(result.tools)


async def call_stdio_tool(upstream: StdioUpstream | dict[str, Any], name: str,
                          arguments: dict[str, Any]) -> Any:
    """Forward one tool call to a stdio upstream."""
    config = _upstream(upstream)
    async with _stdio_session(config) as session:
        return await session.call_tool(name, arguments)


def serve_proxy(*, upstream: StdioUpstream | dict[str, Any], sink: TraceSink,
                capture_id: str, episode_id: str = "ep_proxy",
                name: str = "jdsl-mcp-proxy") -> None:  # pragma: no cover - needs live MCP host
    """Serve the stdio MCP proxy on this process's stdin/stdout."""
    try:
        import anyio
        from mcp.server.stdio import stdio_server
    except ImportError as e:
        raise RuntimeError("the MCP proxy transport needs the 'mcp' package: uv sync --extra harness") from e

    async def run() -> None:
        server = build_stdio_proxy_server(upstream, sink, capture_id=capture_id,
                                          episode_id=episode_id, name=name)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(run)


def _upstream(value: StdioUpstream | dict[str, Any]) -> StdioUpstream:
    return value if isinstance(value, StdioUpstream) else StdioUpstream(**value)


def _as_mcp_tool(tool: ProxiedTool) -> Any:
    from mcp import types
    return types.Tool(name=tool.namespaced, description=tool.description,
                      inputSchema=tool.input_schema, outputSchema=tool.output_schema or None)


def _dump_mcp_result(result: Any) -> Any:
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured
    content = getattr(result, "content", None)
    parsed = [_maybe_json(getattr(block, "text", None)) for block in (content or [])
              if getattr(block, "type", None) == "text"]
    parsed = [item for item in parsed if item is not None]
    if len(parsed) == 1:
        return parsed[0]
    if parsed:
        return parsed
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)
    return result


def _maybe_json(text: Any) -> Any:
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped)
    except ValueError:
        return None


def _stdio_params(config: StdioUpstream) -> Any:
    from mcp.client.stdio import StdioServerParameters
    env = None if config.env is None else {**os.environ, **config.env}
    return StdioServerParameters(command=config.command, args=config.args, env=env, cwd=config.cwd)


def _stdio_session(config: StdioUpstream) -> Any:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session_scope():
        from mcp.client.session import ClientSession
        from mcp.client.stdio import stdio_client
        async with stdio_client(_stdio_params(config)) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    return session_scope()


__all__ = [
    "ProxiedTool",
    "record_proxied_call",
    "MCPProxy",
    "StdioUpstream",
    "build_stdio_proxy_server",
    "discover_stdio_tools",
    "call_stdio_tool",
    "serve_proxy",
]
