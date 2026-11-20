"""The MCP server (app/mcp/server.py) is a thin wrapper around
list_anomalies_for/list_duplicates_for/semantic_search that resolves a
caller's scope once from a JWT and calls these same service functions -
so what actually needs testing is that those service functions enforce
the same role-visibility scoping every other entry point in this app
does (see .claude/rules/security-and-multitenancy.md Rule 1), plus that
the YAML semantic model file is well-formed. Importing app.mcp.server
itself would require the `mcp` package to be installed, which isn't a
given in every environment that runs this test file; the service
functions it wraps have no such dependency.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_visible_user_ids
from app.models.user import User
from app.services.anomalies import list_anomalies_for
from app.services.duplicates import list_duplicates_for

_METRICS_YAML_PATH = Path(__file__).resolve().parent.parent / "app" / "mcp" / "metrics.yaml"


def _register_and_login(client: TestClient, email: str, role_attempt: str | None = None) -> dict:
    payload = {"email": email, "password": "pass1234567", "full_name": "Test"}
    if role_attempt:
        payload["role"] = role_attempt
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 201
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload_and_process(client: TestClient, headers: dict, csv: bytes) -> int:
    r = client.post("/documents/upload", files={"file": ("t.csv", csv, "text/csv")}, headers=headers)
    doc_id = r.json()["id"]
    client.post(f"/documents/{doc_id}/process", headers=headers)
    return doc_id


def _anomaly_csv() -> bytes:
    rows = [b"description,quantity,unit_price,total,supplier"]
    for _ in range(10):
        rows.append(b"MCP Widget,1,10.00,10.00,Supplier X")
    rows.append(b"MCP Widget,1,10000.00,10000.00,Supplier X")
    return b"\n".join(rows)


def _duplicate_csv() -> bytes:
    return (
        b"description,quantity,unit_price,total,supplier\n"
        b"MCP toner cartridge HP LaserJet 415A,1,50.00,50.00,Office Depot\n"
        b"MCP toner cartridge HP LaserJet 415A,1,50.00,50.00,Office Depot"
    )


def test_list_anomalies_for_respects_role_scope(client: TestClient, db: Session):
    buyer_headers = _register_and_login(client, "mcp-anom-buyer@spend.com")
    doc_id = _upload_and_process(client, buyer_headers, _anomaly_csv())
    item_ids = {i["id"] for i in client.get(f"/documents/{doc_id}", headers=buyer_headers).json()["line_items"]}

    buyer = db.query(User).filter(User.email == "mcp-anom-buyer@spend.com").first()
    buyer_scope = get_visible_user_ids(buyer, db)
    buyer_results = list_anomalies_for(db, buyer_scope)
    assert any(r["id"] in item_ids for r in buyer_results)

    _register_and_login(client, "mcp-anom-finance@spend.com", role_attempt="finance")
    finance = db.query(User).filter(User.email == "mcp-anom-finance@spend.com").first()
    finance_scope = get_visible_user_ids(finance, db)
    finance_results = list_anomalies_for(db, finance_scope)
    assert not any(r["id"] in item_ids for r in finance_results)

    admin_results = list_anomalies_for(db, None)
    assert any(r["id"] in item_ids for r in admin_results)


def test_list_duplicates_for_respects_role_scope(client: TestClient, db: Session):
    buyer_headers = _register_and_login(client, "mcp-dup-buyer@spend.com")
    doc_id = _upload_and_process(client, buyer_headers, _duplicate_csv())
    item_ids = {i["id"] for i in client.get(f"/documents/{doc_id}", headers=buyer_headers).json()["line_items"]}

    buyer = db.query(User).filter(User.email == "mcp-dup-buyer@spend.com").first()
    buyer_scope = get_visible_user_ids(buyer, db)
    buyer_groups = list_duplicates_for(db, buyer_scope)
    assert any(set(it["id"] for it in g["items"]) & item_ids for g in buyer_groups)

    _register_and_login(client, "mcp-dup-finance@spend.com", role_attempt="finance")
    finance = db.query(User).filter(User.email == "mcp-dup-finance@spend.com").first()
    finance_scope = get_visible_user_ids(finance, db)
    finance_groups = list_duplicates_for(db, finance_scope)
    assert not any(set(it["id"] for it in g["items"]) & item_ids for g in finance_groups)

    admin_groups = list_duplicates_for(db, None)
    assert any(set(it["id"] for it in g["items"]) & item_ids for g in admin_groups)


_REQUIRED_METRIC_FIELDS = {"name", "definition", "calculation", "source"}


def test_metrics_semantic_model_is_well_formed():
    parsed = yaml.safe_load(_METRICS_YAML_PATH.read_text(encoding="utf-8"))
    assert "metrics" in parsed
    metrics = parsed["metrics"]
    assert len(metrics) >= 5
    names = [m["name"] for m in metrics]
    assert len(names) == len(set(names)), "metric names must be unique"
    for metric in metrics:
        missing = _REQUIRED_METRIC_FIELDS - metric.keys()
        assert not missing, f"metric {metric.get('name')} is missing fields: {missing}"


def _metrics() -> list[dict]:
    return yaml.safe_load(_METRICS_YAML_PATH.read_text(encoding="utf-8"))["metrics"]


@pytest.mark.parametrize("metric", _metrics(), ids=lambda m: m["name"])
def test_every_metric_source_resolves_to_a_real_callable(metric):
    # The semantic model is documentation, so nothing else stops it drifting
    # from the code: a renamed or removed function must fail this test.
    module_path, _, attr = metric["source"].rpartition(".")
    fn = getattr(importlib.import_module(module_path), attr, None)
    assert callable(fn), f"metric {metric['name']}: source {metric['source']} does not resolve to a function"


@pytest.mark.parametrize("metric", [m for m in _metrics() if "threshold_setting" in m], ids=lambda m: m["name"])
def test_metric_threshold_settings_exist(metric):
    assert hasattr(settings, metric["threshold_setting"].lower()), metric["threshold_setting"]


def test_metrics_cover_the_mcp_ranking_tools():
    names = {m["name"] for m in _metrics()}
    assert {"top_expenses", "spend_by_supplier"} <= names
