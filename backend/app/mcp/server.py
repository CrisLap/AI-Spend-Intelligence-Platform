"""MCP server exposing spend search, anomalies and duplicates.

Three read-only tools (search_spend, list_anomalies, list_duplicates) plus
a `metrics://semantic-model` resource describing every metric this
platform computes (see metrics.yaml). Every tool call is scoped to the
caller's visible spend-data scope exactly the way every other entry point
in this app is - see core/deps.py::get_visible_user_ids - so an MCP client
never sees more than the equivalent FastAPI route would return for the
same user.

Authentication: the caller must provide MCP_AUTH_TOKEN, a JWT obtained the
normal way via POST /auth/login. It is decoded with the exact
decode_access_token() the FastAPI routes use (app/core/security.py) - no
separate auth mechanism for this entry point. _current_scope() re-resolves
the token and the caller's get_visible_user_ids() scope on every tool
call, the same as every FastAPI route does per-request - it is
deliberately NOT cached for the life of the process, so a role change
(e.g. an admin demoting/promoting this token's owner, see
users.py::update_user_role) while the server is running takes effect on
the very next tool call instead of only after a restart. The same check
also runs once at import time purely to fail fast on a missing/invalid
token at startup rather than only on the first tool call; this startup
check is a one-time local bootstrap, not a request path, so it is
deliberately exempt from the "provider wrapper never raises" convention
the rest of this app follows for Ollama/Groq/Jina/Qdrant calls.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

from app.core.database import SessionLocal
from app.core.deps import get_visible_user_ids
from app.core.security import decode_access_token
from app.models.user import User
from app.services.anomalies import list_anomalies_for
from app.services.duplicates import list_duplicates_for
from app.services.search import semantic_search

_METRICS_YAML_PATH = Path(__file__).parent / "metrics.yaml"


def _current_scope(db) -> int | list[int] | None:
    token = os.environ.get("MCP_AUTH_TOKEN")
    if not token:
        raise RuntimeError(
            "MCP_AUTH_TOKEN is not set. Obtain a JWT via POST /auth/login and "
            "pass it as the MCP_AUTH_TOKEN environment variable when starting "
            "this server."
        )
    payload = decode_access_token(token)
    if payload is None:
        raise RuntimeError("MCP_AUTH_TOKEN is invalid or expired - log in again to get a fresh token.")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None or not user.is_active:
        raise RuntimeError("MCP_AUTH_TOKEN refers to an unknown or disabled user.")
    return get_visible_user_ids(user, db)


def _fail_fast_on_bad_token() -> None:
    db = SessionLocal()
    try:
        _current_scope(db)
    finally:
        db.close()


_fail_fast_on_bad_token()

mcp = FastMCP(
    "ai-spend-intelligence",
    instructions=(
        "Tools for the AI Spend Intelligence Platform: semantic spend search, "
        "flagged anomalies and flagged duplicate line items, scoped to the "
        "authenticated caller's visible data. Read the metrics://semantic-model "
        "resource for the exact definition and calculation rule of a metric "
        "before quoting a number derived from one of these tools."
    ),
)


@mcp.tool()
def search_spend(query: str, top_k: int = 10) -> list[dict]:
    """Semantic search over spend line items visible to the authenticated
    caller. Returns up to top_k matches, each with description, supplier,
    total, category and a similarity score. Not a ranking by amount - use
    this for "find spend related to X", not "highest/biggest spend"."""
    db = SessionLocal()
    try:
        scope = _current_scope(db)
        return semantic_search(query, top_k=top_k, user_id=scope, db=db)
    finally:
        db.close()


@mcp.tool()
def list_anomalies(limit: int = 50, include_resolved: bool = False) -> list[dict]:
    """List flagged spend anomalies (price/quantity z-score outliers, new
    suppliers - see the anomaly_zscore entry in metrics://semantic-model)
    visible to the authenticated caller, most significant first."""
    db = SessionLocal()
    try:
        scope = _current_scope(db)
        return list_anomalies_for(db, scope, limit=limit, include_resolved=include_resolved)
    finally:
        db.close()


@mcp.tool()
def list_duplicates(limit: int = 50, include_resolved: bool = False) -> list[dict]:
    """List flagged duplicate line-item groups (exact or semantic matches -
    see the duplicate_similarity entry in metrics://semantic-model) visible
    to the authenticated caller, most recent first."""
    db = SessionLocal()
    try:
        scope = _current_scope(db)
        return list_duplicates_for(db, scope, limit=limit, include_resolved=include_resolved)
    finally:
        db.close()


@mcp.resource("metrics://semantic-model")
def semantic_model() -> dict:
    """The semantic model for this platform: name, definition and
    calculation rule for every metric it computes, parsed from
    app/mcp/metrics.yaml."""
    return yaml.safe_load(_METRICS_YAML_PATH.read_text(encoding="utf-8"))
