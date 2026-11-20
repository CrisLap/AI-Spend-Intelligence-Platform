"""MCP server (app/mcp/server.py): per-request bearer auth on the HTTP
transports, the stdio env-token path, tool registration and role scoping of
the two deterministic tools (top_expenses, spend_by_supplier).

The tools open their own SessionLocal(), so it is monkeypatched to the test
database; the HTTP request context is stubbed with a bare namespace since
only `request_context.request.headers` is read.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.mcp import server as mcp_server
from app.models.user import User
from tests.conftest import TestSessionLocal
from tests.test_mcp_tools import _register_and_login, _upload_and_process


def _http_ctx(authorization: str | None):
    headers = {} if authorization is None else {"authorization": authorization}
    return SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(headers=headers)))


def _token_for(db: Session, email: str) -> str:
    user = db.query(User).filter(User.email == email).first()
    return create_access_token(user.id, user.role)


@pytest.fixture
def mcp_db(monkeypatch):
    monkeypatch.setattr(mcp_server, "SessionLocal", TestSessionLocal)


def test_expected_tools_are_registered():
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert names == {"search_spend", "top_expenses", "spend_by_supplier", "list_anomalies", "list_duplicates"}


def test_http_without_bearer_is_refused_even_if_env_token_is_set(client: TestClient, db: Session, monkeypatch):
    _register_and_login(client, "mcp-http-noauth@spend.com")
    monkeypatch.setenv("MCP_AUTH_TOKEN", _token_for(db, "mcp-http-noauth@spend.com"))
    # The process owner's env token must never serve an anonymous HTTP caller.
    with pytest.raises(RuntimeError, match="Authorization"):
        mcp_server._current_scope(db, _http_ctx(None))
    with pytest.raises(RuntimeError, match="Authorization"):
        mcp_server._current_scope(db, _http_ctx("Basic abc"))


def test_http_invalid_bearer_is_refused(db: Session):
    with pytest.raises(RuntimeError, match="invalid or expired"):
        mcp_server._current_scope(db, _http_ctx("Bearer not-a-jwt"))


def test_http_bearer_resolves_the_callers_role_scope(client: TestClient, db: Session):
    _register_and_login(client, "mcp-http-scope@spend.com")
    token = _token_for(db, "mcp-http-scope@spend.com")
    me = db.query(User).filter(User.email == "mcp-http-scope@spend.com").first()
    scope = mcp_server._current_scope(db, _http_ctx(f"Bearer {token}"))
    assert isinstance(scope, list) and me.id in scope


def test_stdio_uses_env_token_and_requires_it(client: TestClient, db: Session, monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="MCP_AUTH_TOKEN is not set"):
        mcp_server._current_scope(db, None)
    _register_and_login(client, "mcp-stdio@spend.com")
    monkeypatch.setenv("MCP_AUTH_TOKEN", _token_for(db, "mcp-stdio@spend.com"))
    assert mcp_server._current_scope(db, None) is not None


def test_top_expenses_and_spend_by_supplier_respect_role_scope(client: TestClient, db: Session, mcp_db, monkeypatch):
    csv = (
        b"description,quantity,unit_price,total,supplier\n"
        # Larger than any amount other tests put in the shared test database.
        b"MCP big item,1,123456789012.34,123456789012.34,McpSupplierZeta\n"
        b"MCP small item,2,10.00,20.00,McpSupplierZeta"
    )
    buyer_headers = _register_and_login(client, "mcp-rank-buyer@spend.com")
    doc_id = _upload_and_process(client, buyer_headers, csv)
    item_ids = {i["id"] for i in client.get(f"/documents/{doc_id}", headers=buyer_headers).json()["line_items"]}
    _register_and_login(client, "mcp-rank-finance@spend.com", role_attempt="finance")

    monkeypatch.setenv("MCP_AUTH_TOKEN", _token_for(db, "mcp-rank-buyer@spend.com"))
    top = mcp_server.top_expenses(limit=3)
    assert top[0]["total"] == 123456789012.34  # a real ranking: the largest item is first
    assert top[0]["id"] in item_ids
    assert [r["total"] for r in top] == sorted((r["total"] for r in top), reverse=True)
    by_supplier = {r["supplier"]: r for r in mcp_server.spend_by_supplier(limit=100)}
    assert by_supplier["McpSupplierZeta"]["total"] == pytest.approx(123456789012.34 + 20.00)
    assert by_supplier["McpSupplierZeta"]["count"] == 2

    # Another role never sees the buyer's records through either tool.
    monkeypatch.setenv("MCP_AUTH_TOKEN", _token_for(db, "mcp-rank-finance@spend.com"))
    assert not any(r["id"] in item_ids for r in mcp_server.top_expenses(limit=50))
    assert "McpSupplierZeta" not in {r["supplier"] for r in mcp_server.spend_by_supplier(limit=100)}
