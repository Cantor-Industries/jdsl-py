"""A tiny retail MCP server for exercising the jdsl harness end-to-end in a real
host (Claude Code / Gemini CLI).

Why this exists: host hooks (Tier B) can only mine exact dataflow when a tool
returns *structured* JSON — a discrete id in one tool's result reappearing in a
later tool's argument (design §16.1). A host's native filesystem/shell tools
return text blobs, so the id-copy is buried in a string and nothing compiles.
These MCP tools return dicts/lists, so `lookup -> list_orders -> get_order ->
cancel` produces the same clean lineage as the built-in retail fixture — captured
through the *real* host this time.

Run it as an MCP server (needs the `mcp` SDK: `uv sync --extra harness`):

    uv run --extra harness python examples/harness/retail_mcp_server.py

Register it with Claude Code (project-local `.mcp.json`):

    { "mcpServers": { "retail": {
        "command": "uv",
        "args": ["run", "--extra", "harness", "python",
                 "examples/harness/retail_mcp_server.py"] } } }

Then, with `jdsl harness serve` running and the capture hook installed, ask the
host the SAME task over several DIFFERENT emails below (each a separate session =
one episode). `email` varies with no dataflow source -> a free run input; the ids
flow between tools -> dataflow refs. Compile once you have ~5 episodes.
"""

from __future__ import annotations

# Fake catalogue. Distinct customer ids and order ids per email so lineage is real,
# not coincidental. A "pending" order in each set is the one a cancel task targets —
# that pick is the single residual decision the small model keeps.
_CUSTOMERS: dict[str, dict] = {
    "ada@example.com":     {"id": "C_ada",  "name": "Ada"},
    "bo@example.com":      {"id": "C_bo",   "name": "Bo"},
    "cass@example.com":    {"id": "C_cass", "name": "Cass"},
    "dev@example.com":     {"id": "C_dev",  "name": "Dev"},
    "el@example.com":      {"id": "C_el",   "name": "El"},
}

_ORDERS: dict[str, list[dict]] = {
    "C_ada":  [{"id": "O_ada_1", "status": "shipped"},  {"id": "O_ada_2", "status": "pending"}],
    "C_bo":   [{"id": "O_bo_1",  "status": "pending"},  {"id": "O_bo_2",  "status": "delivered"}],
    "C_cass": [{"id": "O_cass_1", "status": "delivered"}, {"id": "O_cass_2", "status": "pending"}],
    "C_dev":  [{"id": "O_dev_1", "status": "pending"},  {"id": "O_dev_2", "status": "shipped"}],
    "C_el":   [{"id": "O_el_1",  "status": "shipped"},  {"id": "O_el_2",  "status": "pending"}],
}

_CANCELLED: set[str] = set()


def _new_server(name: str):
    """Return a decorator-style MCP server, across SDK versions: `MCPServer` on
    mcp >= 2.0, `FastMCP` on mcp 1.x. Both expose `.tool()` and `.run()`."""
    try:
        from mcp.server import MCPServer  # type: ignore  # mcp >= 2.0
        return MCPServer(name)
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore  # mcp 1.x
        return FastMCP(name)
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "this example needs the MCP SDK: run `uv sync --extra harness` first") from e


def _build_server():
    mcp = _new_server("retail")

    @mcp.tool()
    def lookup(email: str) -> dict:
        """Resolve a customer by email. Returns {id, name, email}."""
        cust = _CUSTOMERS.get(email.strip().lower())
        if cust is None:
            raise ValueError(f"no customer for {email!r}")
        return {**cust, "email": email}

    @mcp.tool()
    def list_orders(customer_id: str) -> list[dict]:
        """List a customer's orders as [{id, status}, ...]."""
        return _ORDERS.get(customer_id, [])

    @mcp.tool()
    def get_order(order_id: str) -> dict:
        """Fetch a single order by id."""
        for orders in _ORDERS.values():
            for o in orders:
                if o["id"] == order_id:
                    return {**o, "cancelled": order_id in _CANCELLED}
        raise ValueError(f"no order {order_id!r}")

    @mcp.tool()
    def cancel(order_id: str) -> dict:
        """Cancel an order by id. Returns {ok, cancelled}."""
        _CANCELLED.add(order_id)
        return {"ok": True, "cancelled": order_id}

    return mcp


if __name__ == "__main__":
    _build_server().run()  # stdio transport by default
