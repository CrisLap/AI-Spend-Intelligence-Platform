from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.document import Document, LineItem
from app.services.agents.react_engine import Tool
from app.services.analytics import forecast_next_month_spend, get_dashboard, get_supplier_variance
from app.services.anomalies import detect_anomalies
from app.services.contract_intelligence import search_contracts

_IGNORED_INPUTS = {"", "all", "*", "any", "n/a", "none"}


def _spend_overview_tool(user_id: int, db: Session):
    def _call(_query: str) -> str:
        data = get_dashboard(user_id=user_id, db=db)
        suppliers = ", ".join(f"{s['supplier']} (€{s['total']:,.2f})" for s in data["top_suppliers"][:5])
        categories = ", ".join(
            f"{c['category']} (€{c['total']:,.2f}, {c['percentage']}%)" for c in data["top_categories"]
        )
        return (
            f"Total spend: €{data['total_spend']:,.2f} across {data['total_items']} line items "
            f"in {data['total_documents']} documents.\n"
            f"Anomalies flagged: {data['anomaly_count']}. Duplicate groups: {data['duplicate_count']}.\n"
            f"Top suppliers by spend: {suppliers or 'none'}.\n"
            f"Top categories by spend: {categories or 'none'}."
        )

    return _call


def _supplier_variance_tool(user_id: int, db: Session):
    def _call(query: str) -> str:
        variances = get_supplier_variance(user_id=user_id, db=db)
        if not variances:
            return (
                "Not enough historical data per supplier to compute spend "
                "variance (each supplier needs at least 4 line items)."
            )
        q = (query or "").strip().lower()
        if q not in _IGNORED_INPUTS:
            matched = [v for v in variances if q in v["supplier"].lower()]
            if matched:
                variances = matched
        lines = [
            f"{v['supplier']}: {v['variance_pct']:+.1f}% "
            f"(€{v['previous_total']:,.2f} -> €{v['recent_total']:,.2f}), "
            f"categories: {', '.join(v['categories']) or 'n/a'}"
            for v in variances[:8]
        ]
        return "\n".join(lines)

    return _call


def _anomaly_scan_tool(user_id: int, db: Session):
    def _call(_query: str) -> str:
        items = db.query(LineItem).join(Document).filter(Document.user_id == user_id).all()
        if not items:
            return "No line items found for this user."
        results = detect_anomalies(items, db=db)
        flagged = [r for r in results if r["is_anomaly"]]
        if not flagged:
            return "No anomalies detected in current spend data."
        return "\n".join(
            f"{r['description']} (category: {r['category'] or 'n/a'}, z-score {r['zscore']:.2f}): {r['reason']}"
            for r in flagged[:10]
        )

    return _call


def _contract_search_tool(user_id: int, db: Session):
    def _call(query: str) -> list[dict]:
        return search_contracts(query, top_k=5, user_id=user_id, db=db)

    return _call


def _top_expenses_tool(user_id: int, db: Session):
    def _call(query: str) -> str:
        q = (query or "").strip()
        n = int(q) if q.isdigit() else 5
        n = max(1, min(n, 20))
        rows = (
            db.query(LineItem, Document.original_name)
            .join(Document, LineItem.document_id == Document.id)
            .filter(Document.user_id == user_id)
            .order_by(LineItem.total.desc())
            .limit(n)
            .all()
        )
        if not rows:
            return "No line items found for this user."
        return "\n".join(
            f"€{item.total:,.2f} - {item.description} - {item.supplier or 'unknown supplier'} "
            f"(category: {item.category_label or 'n/a'}, source: {doc_name}, invoice: {item.invoice_number or 'n/a'})"
            for item, doc_name in rows
        )

    return _call


def top_expenses_tool_for(user_id: int, db: Session) -> Tool:
    return Tool(
        name="top_expenses",
        description=(
            "get the single line items with the highest total spend, sorted "
            "descending by amount - a real ranking over all records, not a "
            'semantic search. Use this for "highest/biggest/most expensive" '
            'questions. Input: how many to return (e.g. "5"); defaults to 5.'
        ),
        fn=_top_expenses_tool(user_id, db),
    )


def _forecast_tool(user_id: int, db: Session):
    def _call(_query: str) -> str:
        result = forecast_next_month_spend(user_id=user_id, db=db)
        if not result["available"]:
            return result["reason"]
        history = ", ".join(f"{m}: €{t:,.2f}" for m, t in zip(result["months"], result["monthly_totals"]))
        return (
            f"Monthly spend history: {history}.\n"
            f"Linear trend: €{result['trend_per_month']:+,.2f}/month.\n"
            f"Forecast for next month: €{result['forecast_next_month']:,.2f}."
        )

    return _call


def contract_search_tool_for(user_id: int, db: Session) -> Tool:
    return Tool(
        name="contract_search",
        description=(
            "semantic search over indexed contract text - e.g. auto-renewal "
            "clauses, expiration dates, penalty terms. Input: a search query."
        ),
        fn=_contract_search_tool(user_id, db),
    )


def forecast_tool_for(user_id: int, db: Session) -> Tool:
    return Tool(
        name="forecast_spend",
        description=(
            "get a linear-trend forecast of next month's total spend based on "
            'monthly history. Input is ignored - pass "forecast".'
        ),
        fn=_forecast_tool(user_id, db),
    )


def build_tools(user_id: int, db: Session) -> list[Tool]:
    """The Cost Saving Agent's tool registry - each tool wraps an existing,
    already-tested service function so every number the agent reasons over
    is a real query result, not a fabricated figure."""
    return [
        Tool(
            name="spend_overview",
            description=(
                "get an overview of total spend, top suppliers and top spend "
                'categories. Input is ignored - pass "overview".'
            ),
            fn=_spend_overview_tool(user_id, db),
        ),
        Tool(
            name="supplier_variance",
            description=(
                "get period-over-period spend variance per supplier (which "
                "suppliers' spend increased or decreased, and by how much). "
                'Input: a supplier name to filter, or "all".'
            ),
            fn=_supplier_variance_tool(user_id, db),
        ),
        Tool(
            name="anomaly_scan",
            description=(
                "scan spend line items for price, quantity and new-supplier "
                'anomalies. Input is ignored - pass "scan".'
            ),
            fn=_anomaly_scan_tool(user_id, db),
        ),
        contract_search_tool_for(user_id, db),
    ]


def build_forecast_tools(user_id: int, db: Session) -> list[Tool]:
    """The Forecast Agent's tool registry: just the forecast itself, plus
    the same spend overview the Cost Saving Agent uses for context - kept
    deliberately narrow so this agent stays focused on one question."""
    return [forecast_tool_for(user_id, db), Tool(
        name="spend_overview",
        description='get an overview of total spend and top categories. Input is ignored - pass "overview".',
        fn=_spend_overview_tool(user_id, db),
    )]


def build_contract_risk_tools(user_id: int, db: Session) -> list[Tool]:
    """The Contract Risk Agent's tool registry: reuses the exact same
    contract_search tool the Cost Saving Agent uses for renewal clauses -
    only the system prompt and search queries around it differ (see
    cost_saving_agent.py's _CONTRACT_RISK_SEARCH_QUERIES)."""
    return [contract_search_tool_for(user_id, db)]
