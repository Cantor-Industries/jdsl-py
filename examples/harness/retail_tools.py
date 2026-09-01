"""Host-tool bindings for running the compiled ``retail.jdsl`` behavior
(design §12.1 binding, §40 runtime).

A compiled package is portable IR: it names *logical* capabilities and the exact
dataflow between them, but carries no implementations. To run it you bind each
required capability to a real callable via a ``TOOLS`` dict (``logical_id ->
callable``). ``jdsl package run <pkg> --tools this_file.py`` imports this module,
reads ``TOOLS``, and lowers the IR onto these functions.

Return shapes matter: the runtime extracts wired arguments by navigating the exact
path recorded at capture time. For this package (see ``behavior.json``):

    list_orders.customer_id  <-  lookup(...).id                     # a bare dict
    get_order.order_id       <-  list_orders(...).result[0].id      # MCP {"result": [...]}

So ``lookup`` returns a bare ``{"id": ...}`` while ``list_orders`` returns the
``{"result": [...]}`` envelope — mirroring how each arrived through the MCP host
when the behavior was captured. Change these shapes and the wiring path breaks.

These are the same fake records as ``retail_mcp_server.py``, as plain in-process
functions (no MCP transport needed to *run* a compiled package)."""

from __future__ import annotations

_CUSTOMERS: dict[str, dict] = {
    "ada@example.com":  {"id": "C_ada",  "name": "Ada"},
    "bo@example.com":   {"id": "C_bo",   "name": "Bo"},
    "cass@example.com": {"id": "C_cass", "name": "Cass"},
    "dev@example.com":  {"id": "C_dev",  "name": "Dev"},
    "el@example.com":   {"id": "C_el",   "name": "El"},
}
_ORDERS: dict[str, list[dict]] = {
    "C_ada":  [{"id": "O_ada_1", "status": "shipped"},   {"id": "O_ada_2", "status": "pending"}],
    "C_bo":   [{"id": "O_bo_1",  "status": "pending"},   {"id": "O_bo_2",  "status": "delivered"}],
    "C_cass": [{"id": "O_cass_1", "status": "delivered"}, {"id": "O_cass_2", "status": "pending"}],
    "C_dev":  [{"id": "O_dev_1", "status": "pending"},   {"id": "O_dev_2", "status": "shipped"}],
    "C_el":   [{"id": "O_el_1",  "status": "shipped"},   {"id": "O_el_2",  "status": "pending"}],
}


def _tool_search(query: str = "", max_results: int = 5) -> dict:
    """A stub for the host's ToolSearch. The behavior begins with it because the
    capturing session had to load deferred MCP schemas; nothing reads its result,
    so it just needs to exist to satisfy the required capability."""
    return {"matches": [q for q in query.removeprefix("select:").split(",") if q][:max_results]}


def _lookup(email: str) -> dict:
    """Resolve a customer by email -> bare {id, name, email} (wired via `.id`)."""
    cust = _CUSTOMERS.get(email.strip().lower())
    if cust is None:
        raise ValueError(f"no customer for {email!r}")
    return {**cust, "email": email}


def _list_orders(customer_id: str) -> dict:
    """List orders -> {"result": [{id, status}, ...]} (wired via `.result[0].id`)."""
    return {"result": _ORDERS.get(customer_id, [])}


def _get_order(order_id: str) -> dict:
    """Fetch one order by id (terminal step)."""
    for orders in _ORDERS.values():
        for o in orders:
            if o["id"] == order_id:
                return {**o, "cancelled": False}
    raise ValueError(f"no order {order_id!r}")


TOOLS = {
    "ToolSearch": _tool_search,
    "mcp__retail__lookup": _lookup,
    "mcp__retail__list_orders": _list_orders,
    "mcp__retail__get_order": _get_order,
}
