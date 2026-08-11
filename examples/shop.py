"""A tool-heavy ReAct agent: an order-total assistant over a tiny store.

This exercises tools hard — the model can't answer in one shot. It must: search
the catalog, inspect several products, *compare* them to pick the cheapest match
that's actually in stock, then chain arithmetic across three more tools (quantity
→ coupon → shipping → total). The tools are deterministic; the model only
orchestrates. That split — deterministic tools, model-driven control — is the
whole point of react.

Run it:
  uv run jdsl run examples/shop.py \\
      -i request="Order 3 of the cheapest wireless mouse in stock, coupon SAVE15, ship to Kenya"
"""

from jdsl import react, root, tool

# sku -> (name, price, stock, tags)
_CATALOG = {
    "M1": ("Basic Wireless Mouse", 12.99, 40, "mouse wireless"),
    "M2": ("Pro Wireless Mouse", 24.50, 0, "mouse wireless"),      # out of stock
    "M3": ("Budget Wireless Mouse", 9.99, 15, "mouse wireless"),   # cheapest in stock
    "M4": ("Wired Mouse", 6.99, 100, "mouse wired"),               # not wireless
    "K1": ("Mechanical Keyboard", 79.00, 8, "keyboard wired"),
}
_COUPONS = {"SAVE10": 10.0, "SAVE15": 15.0}
_SHIP_PER_ITEM = {"kenya": 5.0, "usa": 3.0, "japan": 8.0}


@tool
def find_products(query: str) -> list[str]:
    """Search the catalog; return matching SKUs. Match is on name + tags."""
    q = query.lower().split()
    return [sku for sku, (name, *_rest, tags) in _CATALOG.items()
            if all(w in f"{name} {tags}".lower() for w in q)]


@tool
def product(sku: str) -> dict:
    """Full details for a SKU: name, price, stock, tags."""
    if sku not in _CATALOG: return {"error": f"no such sku {sku}"}
    name, price, stock, tags = _CATALOG[sku]
    return {"sku": sku, "name": name, "price": price, "stock": stock, "tags": tags}


@tool
def in_stock(sku: str, quantity: int) -> bool:
    """True if at least `quantity` units of `sku` are available."""
    return sku in _CATALOG and _CATALOG[sku][2] >= quantity


@tool
def coupon_discount(code: str) -> float:
    """Discount percent for a coupon code (0 if unknown/invalid)."""
    return _COUPONS.get(code.strip().upper(), 0.0)


@tool
def shipping_cost(country: str, items: int) -> float:
    """Shipping cost for `items` units to a country."""
    return round(_SHIP_PER_ITEM.get(country.strip().lower(), 12.0) * items, 2)


@tool
def order_total(unit_price: float, quantity: int, discount_percent: float, shipping: float) -> float:
    """Final total: unit_price*quantity, minus discount_percent, plus shipping."""
    subtotal = unit_price * quantity
    return round(subtotal * (1 - discount_percent / 100) + shipping, 2)


skill = (
    root("Shop", system="You are a meticulous ordering assistant. Never guess prices, stock, "
                        "or totals — always use the tools. Compare options before choosing.")
    .model("deepseek-chat")
    .do(react("request -> answer",
              tools=[find_products, product, in_stock, coupon_discount, shipping_cost, order_total],
              max_steps=12))
)


if __name__ == "__main__":
    ctx = skill.run(request="Order 3 of the cheapest wireless mouse in stock, coupon SAVE15, "
                            "ship 3 items to Kenya. What's my total?")
    print("answer:", ctx.blackboard.get("answer"))
    # expected: cheapest in-stock wireless = M3 @ 9.99 -> 3*9.99=29.97, -15% =25.47, +15 ship = 40.47
