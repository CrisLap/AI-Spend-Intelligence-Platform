"""MCP server exposing spend search, ranking, per-supplier totals, anomalies
and duplicates.

Five read-only tools (search_spend, top_expenses, spend_by_supplier,
list_anomalies, list_duplicates) plus a `metrics://semantic-model` resource
describing every metric this platform computes (see metrics.yaml). Every
number comes from the same deterministic analytics/anomaly/duplicate
functions the REST API uses, never from model-generated text. Every tool call
is scoped to the caller's visible spend-data scope exactly the way every
other entry point in this app is - see core/deps.py::get_visible_user_ids -
so an MCP client never sees more than the equivalent FastAPI route would
return for the same user.

Two transports, one authentication model (a JWT from POST /auth/login,
decoded with the exact decode_access_token() the FastAPI routes use - no
separate auth mechanism for this entry point):

- stdio: the caller provides the JWT once as the MCP_AUTH_TOKEN environment
  variable (a local, single-user process).
- streamable HTTP / SSE: the JWT is read from each request's
  `Authorization: Bearer ...` header, so every call is authenticated on its
  own. The environment token is deliberately NOT used as a fallback here -
  otherwise the process owner's token would silently serve anonymous network
  callers. A request without a valid token is refused.

_current_scope() re-resolves the token and the caller's
get_visible_user_ids() scope on every tool call, the same as every FastAPI
route does per-request - it is deliberately NOT cached for the life of the
process, so a role change (e.g. an admin demoting/promoting this token's
owner, see users.py::update_user_role) while the server is running takes
effect on the very next tool call instead of only after a restart.
check_stdio_token() additionally runs once at stdio startup purely to fail
fast on a missing/invalid token instead of only on the first tool call; this
startup check is a one-time local bootstrap, not a request path, so it is
deliberately exempt from the "provider wrapper never raises" convention the
rest of this app follows for Ollama/Groq/Jina/Qdrant calls.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from mcp.server.fastmcp import Context, FastMCP

from app.core.database import SessionLocal
from app.core.deps import get_visible_user_ids
from app.core.security import decode_access_token
from app.models.user import User
from app.services.analytics import get_spend_by_supplier, get_top_expenses
from app.services.anomalies import list_anomalies_for
from app.services.duplicates import list_duplicates_for
from app.services.search import semantic_search

_METRICS_YAML_PATH = Path(__file__).parent / "metrics.yaml"


def _bearer_from_context(ctx: Context | None) -> tuple[bool, str | None]:
    """Returns (is_http, bearer_token). `is_http` is False for stdio, where
    there is no HTTP request to read a header from."""
    request = None
    if ctx is not None:
        try:
            request = ctx.request_context.request
        except ValueError:
            request = None
    if request is None:
        return False, None
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    return True, value.strip() if scheme.lower() == "bearer" and value.strip() else None


def _current_scope(db, ctx: Context | None = None) -> int | list[int] | None:
    is_http, token = _bearer_from_context(ctx)
    if not is_http:
        token = os.environ.get("MCP_AUTH_TOKEN")
        if not token:
            raise RuntimeError(
                "MCP_AUTH_TOKEN is not set. Obtain a JWT via POST /auth/login and "
                "pass it as the MCP_AUTH_TOKEN environment variable when starting "
                "this server."
            )
    elif not token:
        raise RuntimeError("Missing 'Authorization: Bearer <token>' header - log in via POST /auth/login.")
    payload = decode_access_token(token)
    if payload is None:
        raise RuntimeError("The access token is invalid or expired - log in again to get a fresh token.")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None or not user.is_active:
        raise RuntimeError("The access token refers to an unknown or disabled user.")
    return get_visible_user_ids(user, db)


def check_stdio_token() -> None:
    """Fail fast at stdio startup on a missing/invalid MCP_AUTH_TOKEN."""
    db = SessionLocal()
    try:
        _current_scope(db)
    finally:
        db.close()


mcp = FastMCP(
    "ai-spend-intelligence",
    instructions=(
        "Tools for the AI Spend Intelligence Platform: semantic spend search, "
        "a deterministic ranking of the largest expenses, total spend per "
        "supplier, flagged anomalies and flagged duplicate line items, scoped "
        "to the authenticated caller's visible data. Read the "
        "metrics://semantic-model resource for the exact definition and "
        "calculation rule of a metric before quoting a number derived from "
        "one of these tools."
    ),
)


@mcp.tool()
def search_spend(query: str, top_k: int = 10, ctx: Context | None = None) -> list[dict]:
    """Semantic search over spend line items visible to the authenticated
    caller. Returns up to top_k matches, each with description, supplier,
    total, category and a similarity score. Not a ranking by amount - use
    top_expenses for "highest/biggest spend"."""
    db = SessionLocal()
    try:
        scope = _current_scope(db, ctx)
        return semantic_search(query, top_k=top_k, user_id=scope, db=db)
    finally:
        db.close()


@mcp.tool()
def top_expenses(limit: int = 5, ctx: Context | None = None) -> list[dict]:
    """The single line items with the highest total, descending - a real
    ranking over every visible record, not a semantic-search result (see the
    top_expenses entry in metrics://semantic-model). limit is capped at 50."""
    db = SessionLocal()
    try:
        scope = _current_scope(db, ctx)
        return get_top_expenses(user_id=scope, db=db, limit=limit)
    finally:
        db.close()


@mcp.tool()
def spend_by_supplier(limit: int = 20, ctx: Context | None = None) -> list[dict]:
    """Total spend and line-item count per supplier, highest first (see the
    spend_by_supplier entry in metrics://semantic-model). limit is capped at 100."""
    db = SessionLocal()
    try:
        scope = _current_scope(db, ctx)
        return get_spend_by_supplier(user_id=scope, db=db, limit=limit)
    finally:
        db.close()


@mcp.tool()
def list_anomalies(limit: int = 50, include_resolved: bool = False, ctx: Context | None = None) -> list[dict]:
    """List flagged spend anomalies (price/quantity z-score outliers, new
    suppliers - see the anomaly_zscore entry in metrics://semantic-model)
    visible to the authenticated caller, most significant first."""
    db = SessionLocal()
    try:
        scope = _current_scope(db, ctx)
        return list_anomalies_for(db, scope, limit=limit, include_resolved=include_resolved)
    finally:
        db.close()


@mcp.tool()
def list_duplicates(limit: int = 50, include_resolved: bool = False, ctx: Context | None = None) -> list[dict]:
    """List flagged duplicate line-item groups (exact or semantic matches -
    see the duplicate_similarity entry in metrics://semantic-model) visible
    to the authenticated caller, most recent first."""
    db = SessionLocal()
    try:
        scope = _current_scope(db, ctx)
        return list_duplicates_for(db, scope, limit=limit, include_resolved=include_resolved)
    finally:
        db.close()


@mcp.resource("metrics://semantic-model")
def semantic_model() -> dict:
    """The semantic model for this platform: name, definition and
    calculation rule for every metric it computes, parsed from
    app/mcp/metrics.yaml."""
    return yaml.safe_load(_METRICS_YAML_PATH.read_text(encoding="utf-8"))
