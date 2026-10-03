"""Reusable TUI starters adapted from the runnable examples."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jdsl.ir.schema import (
    BehaviorIR,
    IRAction,
    IRGuard,
    IRInvert,
    IROptional,
    IRPredict,
    IRReact,
    IRRepeat,
    IRSelector,
    IRSequence,
    Signature,
    SignatureInput,
    SignatureOutput,
)
from jdsl.package.manifest import ToolContract, ToolEffects


TemplateFactory = Callable[[], tuple[BehaviorIR, list[ToolContract]]]


@dataclass(frozen=True)
class TemplateDefinition:
    id: str
    title: str
    description: str
    source: str
    factory: TemplateFactory


def _action(node_id: str, tool: str, *, arguments: dict[str, Any] | None = None,
            store: str | None = None) -> IRAction:
    return IRAction(type="action", id=node_id, tool=tool, arguments=arguments or {}, store=store)


def _guard(node_id: str, path: str, value: Any) -> IRGuard:
    return IRGuard(type="guard", id=node_id, expression={"eq": [{"ref": path}, value]})


def _signature(signature_id: str, inputs: tuple[str, ...], output: str, instruction: str,
               *, output_schema: dict[str, Any] | None = None, kind: str = "predict",
               tools: tuple[str, ...] = ()) -> Signature:
    return Signature(
        id=signature_id,
        kind=kind,
        inputs={name: SignatureInput(source=name) for name in inputs},
        output=SignatureOutput(name=output, schema=output_schema or {"type": "string"}),
        instruction=instruction,
        tools=list(tools),
    )


def _contract(logical_id: str, description: str, properties: dict[str, Any] | None = None,
              *, output: dict[str, Any] | None = None, required: tuple[str, ...] = (),
              read_only: bool = True, destructive: bool = False,
              idempotent: bool = True) -> ToolContract:
    return ToolContract(
        logical_id=logical_id,
        description=description,
        input_schema={
            "type": "object",
            "properties": properties or {},
            "required": list(required),
        },
        output_schema=output or {"type": "string"},
        effects=ToolEffects(read_only=read_only, destructive=destructive, idempotent=idempotent),
    )


def _document(root, signatures: tuple[Signature, ...] = (),
              contracts: tuple[ToolContract, ...] = ()) -> tuple[BehaviorIR, list[ToolContract]]:
    return BehaviorIR(root=root, signatures={signature.id: signature for signature in signatures}), list(contracts)


def _greeter() -> tuple[BehaviorIR, list[ToolContract]]:
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            _action("greet", "greet", arguments={"name": {"ref": "name"}}),
        ]),
        contracts=(_contract("greet", "Send a greeting to the supplied name.",
                             {"name": {"type": "string"}}, required=("name",),
                             read_only=False, idempotent=False),),
    )


def _gate() -> tuple[BehaviorIR, list[ToolContract]]:
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            IROptional(type="optional", id="best_effort_audit",
                       child=_action("audit", "audit_access")),
            IRSelector(type="selector", id="authorization", children_=[
                IRSequence(type="sequence", id="admin_branch", children_=[
                    _guard("is_admin", "role", "admin"),
                    _action("grant", "grant_access"),
                ]),
                IRSequence(type="sequence", id="non_banned_branch", children_=[
                    IRInvert(type="invert", id="not_banned",
                             child=_guard("is_banned", "role", "banned")),
                    _action("allow", "allow_access"),
                ]),
            ]),
        ]),
        contracts=(
            _contract("audit_access", "Record an access attempt.", read_only=False, idempotent=False),
            _contract("grant_access", "Grant the authorized role access.", read_only=False, idempotent=False),
            _contract("allow_access", "Allow a non-banned role to proceed.", read_only=False, idempotent=False),
        ),
    )


def _triage() -> tuple[BehaviorIR, list[ToolContract]]:
    category = _signature(
        "classify", ("message",), "category", "Classify the message as billing, support, or other.",
        output_schema={"type": "string", "enum": ["billing", "support", "other"]},
    )
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            IRPredict(type="predict", id="classify_message", signature="classify"),
            IRSelector(type="selector", id="route", children_=[
                IRSequence(type="sequence", id="billing_branch", children_=[
                    _guard("is_billing", "category", "billing"), _action("billing", "route_billing"),
                ]),
                IRSequence(type="sequence", id="support_branch", children_=[
                    _guard("is_support", "category", "support"), _action("support", "route_support"),
                ]),
                _action("human_fallback", "escalate_to_human"),
            ]),
        ]),
        signatures=(category,),
        contracts=(
            _contract("route_billing", "Route the message to the billing queue.", read_only=False, idempotent=False),
            _contract("route_support", "Route the message to the support queue.", read_only=False, idempotent=False),
            _contract("escalate_to_human", "Escalate an unclassified message to a human.", read_only=False, idempotent=False),
        ),
    )


def _pipeline() -> tuple[BehaviorIR, list[ToolContract]]:
    category = _signature(
        "classify_category", ("ticket",), "category",
        "Classify the ticket as bug, billing, or question.",
        output_schema={"type": "string", "enum": ["bug", "billing", "question"]},
    )
    urgency = _signature(
        "classify_urgency", ("ticket",), "urgency",
        "Classify urgency as low or high.",
        output_schema={"type": "string", "enum": ["low", "high"]},
    )
    reply = _signature(
        "draft_reply", ("ticket", "category"), "reply",
        "Draft a concise, friendly customer reply. Do not claim an action occurred unless a tool did it.",
    )
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            IRPredict(type="predict", id="classify_category", signature="classify_category"),
            IRPredict(type="predict", id="classify_urgency", signature="classify_urgency"),
            IRSelector(type="selector", id="urgency_route", children_=[
                IRSequence(type="sequence", id="high_urgency", children_=[
                    _guard("is_high_urgency", "urgency", "high"),
                    _action("page_oncall", "page_oncall"),
                ]),
                _action("log_ticket", "log_ticket"),
            ]),
            IRPredict(type="predict", id="draft_customer_reply", signature="draft_reply"),
        ]),
        signatures=(category, urgency, reply),
        contracts=(
            _contract("page_oncall", "Notify the on-call team about a high-urgency ticket.", read_only=False, idempotent=False),
            _contract("log_ticket", "Record a normal-urgency ticket.", read_only=False, idempotent=False),
        ),
    )


def _reason() -> tuple[BehaviorIR, list[ToolContract]]:
    extract = _signature(
        "extract_facts", ("question",), "key_facts",
        "Identify the relevant facts and constraints briefly. Do not provide hidden chain-of-thought.",
    )
    answer = _signature(
        "answer", ("question", "key_facts"), "answer",
        "Give only the concise final answer, using the supplied facts.",
    )
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            IRPredict(type="predict", id="extract_facts", signature="extract_facts"),
            IRPredict(type="predict", id="final_answer", signature="answer"),
        ]),
        signatures=(extract, answer),
    )


def _refine() -> tuple[BehaviorIR, list[ToolContract]]:
    draft = _signature("draft", ("topic",), "draft", "Write one clear, accurate paragraph about the topic.")
    review = _signature(
        "review", ("draft",), "critique",
        "Give one specific, actionable improvement to the draft.",
    )
    revise = _signature("revise", ("draft", "critique"), "draft",
                        "Revise the draft to address the concrete critique. Preserve correct content.")
    accepted = _signature(
        "acceptance", ("draft", "critique"), "ok",
        "Return 'yes' if the draft is clear and correct; otherwise return 'no'.",
        output_schema={"type": "string", "enum": ["yes", "no"]},
    )
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            IRPredict(type="predict", id="initial_draft", signature="draft"),
            IRRepeat(type="repeat", id="refinement_loop", max=3,
                     until=_guard("accepted", "ok", "yes"),
                     child=IRSequence(type="sequence", id="review_and_revise", children_=[
                         IRPredict(type="predict", id="critique", signature="review"),
                         IRPredict(type="predict", id="check_quality", signature="acceptance"),
                         IRSelector(type="selector", id="revise_if_needed", children_=[
                             _guard("already_accepted", "ok", "yes"),
                             IRPredict(type="predict", id="revise_draft", signature="revise"),
                         ]),
                     ])),
        ]),
        signatures=(draft, review, revise, accepted),
    )


def _react() -> tuple[BehaviorIR, list[ToolContract]]:
    tools = ("lookup_capital", "lookup_population", "multiply")
    agent = _signature("research", ("question",), "answer",
                       "Answer using the tools for factual values. Do not guess. Explain the calculation briefly.",
                       kind="react", tools=tools)
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            IRReact(type="react", id="research", signature="research"),
        ]),
        signatures=(agent,),
        contracts=(
            _contract("lookup_capital", "Look up a country's capital city.",
                      {"country": {"type": "string"}}, required=("country",)),
            _contract("lookup_population", "Look up a city's population.",
                      {"city": {"type": "string"}}, required=("city",),
                      output={"type": "integer"}),
            _contract("multiply", "Multiply two integers.",
                      {"a": {"type": "integer"}, "b": {"type": "integer"}},
                      required=("a", "b"), output={"type": "integer"}),
        ),
    )


def _trip() -> tuple[BehaviorIR, list[ToolContract]]:
    tools = ("distance_km", "drive_hours", "fuel_cost")
    agent = _signature("trip_planner", ("request",), "answer",
                       "Use tools for every distance, duration, and cost. State assumptions and units; do not estimate.",
                       kind="react", tools=tools)
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            IRReact(type="react", id="plan_trip", signature="trip_planner"),
        ]),
        signatures=(agent,),
        contracts=(
            _contract("distance_km", "Road distance between two locations, in kilometers.",
                      {"origin": {"type": "string"}, "destination": {"type": "string"}},
                      required=("origin", "destination"), output={"type": "integer"}),
            _contract("drive_hours", "Estimate driving hours for a distance in kilometers.",
                      {"km": {"type": "integer"}}, required=("km",), output={"type": "number"}),
            _contract("fuel_cost", "Estimate fuel cost for a distance; return amount and currency.",
                      {"km": {"type": "integer"}}, required=("km",), output={"type": "number"}),
        ),
    )


def _shop() -> tuple[BehaviorIR, list[ToolContract]]:
    tools = ("find_products", "get_product", "check_stock", "coupon_discount", "shipping_cost", "order_total")
    agent = _signature(
        "shopping_assistant", ("request",), "answer",
        "Use tools for catalog facts and every calculation. Compare matching in-stock items before recommending. Never place an order unless an explicit order tool is added.",
        kind="react", tools=tools,
    )
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            IRReact(type="react", id="compare_products", signature="shopping_assistant"),
        ]),
        signatures=(agent,),
        contracts=(
            _contract("find_products", "Find catalog items matching a query.",
                      {"query": {"type": "string"}}, required=("query",),
                      output={"type": "array", "items": {"type": "string"}}),
            _contract("get_product", "Return product name, price, inventory, and attributes.",
                      {"sku": {"type": "string"}}, required=("sku",), output={"type": "object"}),
            _contract("check_stock", "Check if a SKU has the requested quantity available.",
                      {"sku": {"type": "string"}, "quantity": {"type": "integer"}},
                      required=("sku", "quantity"), output={"type": "boolean"}),
            _contract("coupon_discount", "Return the valid discount percentage for a coupon.",
                      {"code": {"type": "string"}}, required=("code",), output={"type": "number"}),
            _contract("shipping_cost", "Calculate shipping for an item count and destination.",
                      {"country": {"type": "string"}, "items": {"type": "integer"}},
                      required=("country", "items"), output={"type": "number"}),
            _contract("order_total", "Calculate the final total from price, quantity, discount, and shipping.",
                      {"unit_price": {"type": "number"}, "quantity": {"type": "integer"},
                       "discount_percent": {"type": "number"}, "shipping": {"type": "number"}},
                      required=("unit_price", "quantity", "discount_percent", "shipping"),
                      output={"type": "number"}),
        ),
    )


def _db() -> tuple[BehaviorIR, list[ToolContract]]:
    tools = ("list_tables", "describe_table", "query_rows", "mean")
    agent = _signature(
        "data_analyst", ("question",), "answer",
        "Discover the schema before querying. Use tools for calculations, restrict queries to authorized data, and state relevant limitations.",
        kind="react", tools=tools,
    )
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            IRReact(type="react", id="analyze_data", signature="data_analyst"),
        ]),
        signatures=(agent,),
        contracts=(
            _contract("list_tables", "List tables visible to the current user.",
                      output={"type": "array", "items": {"type": "string"}}),
            _contract("describe_table", "List columns for an authorized table.",
                      {"table": {"type": "string"}}, required=("table",),
                      output={"type": "array", "items": {"type": "string"}}),
            _contract("query_rows", "Query authorized rows using an allowlisted table and column.",
                      {"table": {"type": "string"}, "column": {"type": "string"},
                       "equals": {"type": "string"}}, required=("table", "column", "equals"),
                      output={"type": "array", "items": {"type": "object"}}),
            _contract("mean", "Calculate the arithmetic mean of numeric values.",
                      {"numbers": {"type": "array", "items": {"type": "number"}}},
                      required=("numbers",), output={"type": "number"}),
        ),
    )


def _wiki() -> tuple[BehaviorIR, list[ToolContract]]:
    choose_title = _signature(
        "choose_title", ("titles",), "selected_title",
        "Choose the single title most relevant to the query from the supplied list, verbatim.",
    )
    return _document(
        IRSequence(type="sequence", id="root", children_=[
            _action("search", "search_titles", arguments={"query": {"ref": "query"}}, store="titles"),
            IRPredict(type="predict", id="choose_title", signature="choose_title"),
            _action("fetch", "fetch_content", arguments={"title": {"ref": "selected_title"}}, store="content"),
        ]),
        signatures=(choose_title,),
        contracts=(
            _contract("search_titles", "Search an approved knowledge source and return candidate titles.",
                      {"query": {"type": "string"}}, required=("query",),
                      output={"type": "array", "items": {"type": "string"}}),
            _contract("fetch_content", "Fetch content for an approved title; respect source permissions.",
                      {"title": {"type": "string"}}, required=("title",), output={"type": "string"}),
        ),
    )


TEMPLATES = (
    TemplateDefinition("greeter", "Greeter", "A deterministic action with a typed input capability.", "greeter.py", _greeter),
    TemplateDefinition("gate", "Guarded access", "Best-effort audit, role checks, and a deny-by-default fallback.", "gate.py", _gate),
    TemplateDefinition("triage", "Message triage", "Classify a message, route known categories, and escalate unknowns.", "triage.py", _triage),
    TemplateDefinition("pipeline", "Support workflow", "Classify urgency, route the ticket, then draft a customer reply.", "pipeline.py", _pipeline),
    TemplateDefinition("reason", "Evidence-based answer", "Extract concise facts, then produce a separate final answer.", "reason.py", _reason),
    TemplateDefinition("refine", "Bounded refinement", "Draft, review, and revise with an explicit acceptance check and loop limit.", "refine.py", _refine),
    TemplateDefinition("react", "Research with tools", "Chain typed read tools and a calculation tool to answer a question.", "react.py", _react),
    TemplateDefinition("trip", "Trip planner", "Estimate a route, driving time, and fuel cost through separate capabilities.", "trip.py", _trip),
    TemplateDefinition("shop", "Product comparison", "Compare stock and prices, calculate a total, and never submit an order.", "shop.py", _shop),
    TemplateDefinition("db", "Data analyst", "Discover a schema, query authorized data, and calculate an aggregate.", "db.py", _db),
    TemplateDefinition("wiki", "Knowledge lookup", "Search, select a matching title, then fetch its content.", "wiki.py", _wiki),
)

TEMPLATES_BY_ID = {template.id: template for template in TEMPLATES}


def build_template(template_id: str) -> tuple[BehaviorIR, list[ToolContract]]:
    """Build a fresh behavior tree and contracts for one example-based starter."""
    try:
        return TEMPLATES_BY_ID[template_id].factory()
    except KeyError as error:
        raise ValueError(f"unknown TUI template {template_id!r}") from error


__all__ = ["TEMPLATES", "TEMPLATES_BY_ID", "TemplateDefinition", "build_template"]