"""ERP connectors: field normalization, the import endpoint (role gate,
scoping, audit log, validation) and that an imported document flows through
the normal /process pipeline keeping its supplier and invoice number."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.services.connectors import CsvConnector, MockRestConnector, build_connector
from app.services.connectors.base import MAX_ROWS, rows_to_csv
from app.services.document_intelligence import parse_tabular_items
from tests.test_mcp_tools import _register_and_login

_ERP_CSV = (
    "Item Description,Qty,Unit Price,Vendor,PO Number\n"
    "Industrial stapler,2,12.50,Staples Pro,PO-77\n"
    "Heavy duty shelving,1,310.00,Staples Pro,PO-77\n"
    ",1,5.00,Nobody,PO-78\n"  # no description -> skipped
    "Broken price row,1,abc,Nobody,PO-78\n"  # unparseable amount -> skipped
)


def test_csv_connector_maps_erp_headers_and_skips_unusable_rows():
    result = CsvConnector(_ERP_CSV).fetch()
    assert result.skipped == 2
    assert [(r.description, r.quantity, r.unit_price, r.total, r.supplier, r.invoice_number) for r in result.rows] == [
        ("Industrial stapler", 2.0, 12.5, 25.0, "Staples Pro", "PO-77"),
        ("Heavy duty shelving", 1.0, 310.0, 310.0, "Staples Pro", "PO-77"),
    ]


def test_csv_connector_requires_description_and_amount_columns():
    with pytest.raises(ValueError, match="description"):
        CsvConnector("foo,bar\n1,2\n").fetch()


def test_csv_connector_enforces_row_cap():
    body = "description,total\n" + "x,1\n" * (MAX_ROWS + 1)
    with pytest.raises(ValueError, match="more than"):
        CsvConnector(body).fetch()


def test_mock_rest_connector_normalizes_nested_purchase_orders():
    result = MockRestConnector().fetch()
    assert len(result.rows) == 4 and result.skipped == 0
    rack = next(r for r in result.rows if r.description == "Rack mount kit")
    assert (rack.quantity, rack.unit_price, rack.total) == (4.0, 89.5, 358.0)
    assert (rack.supplier, rack.invoice_number, rack.invoice_date) == ("Acme Corp", "PO-2025-0101", "2025-05-12")


def test_mock_rest_connector_skips_malformed_lines():
    payload = {"purchaseOrders": [{"poNumber": "P1", "vendor": {"name": "V"}, "lines": [
        {"itemDescription": "ok", "qty": 1, "unitPrice": 2},
        {"itemDescription": "no price", "qty": 1},
    ]}]}
    result = MockRestConnector(payload).fetch()
    assert len(result.rows) == 1 and result.skipped == 1


def test_build_connector_rejects_unknown_source_and_empty_csv():
    with pytest.raises(ValueError):
        build_connector("nope")
    with pytest.raises(ValueError):
        build_connector("csv", "  ")


def test_normalized_rows_round_trip_through_the_tabular_parser(tmp_path):
    rows = MockRestConnector().fetch().rows
    path = tmp_path / "erp.csv"
    path.write_bytes(rows_to_csv(rows))
    parsed = parse_tabular_items(str(path), "erp.csv")
    assert [p["total"] for p in parsed] == [r.total for r in rows]
    assert parsed[0]["supplier"] == "Acme Corp" and parsed[0]["invoice_number"] == "PO-2025-0101"


def test_parse_tabular_items_falls_back_when_columns_are_unrecognized(tmp_path):
    path = tmp_path / "weird.csv"
    path.write_text("foo,bar\n1,2\n")
    assert parse_tabular_items(str(path), "weird.csv") is None
    assert parse_tabular_items(str(path), "doc.pdf") is None


def test_import_endpoint_requires_buyer_or_admin_role(client: TestClient):
    finance = _register_and_login(client, "conn-finance@spend.com", role_attempt="finance")
    assert client.post("/connectors/import", json={"source": "mock_rest"}, headers=finance).status_code == 403
    assert client.post("/connectors/import", json={"source": "mock_rest"}).status_code in (401, 403)


def test_import_then_process_keeps_supplier_and_is_scoped_and_audited(client: TestClient, db: Session):
    buyer = _register_and_login(client, "conn-buyer@spend.com")
    r = client.post("/connectors/import", json={"source": "mock_rest"}, headers=buyer)
    assert r.status_code == 201
    body = r.json()
    assert (body["rows_imported"], body["rows_skipped"]) == (4, 0)
    doc_id = body["document"]["id"]

    processed = client.post(f"/documents/{doc_id}/process", headers=buyer)
    assert processed.status_code == 200
    items = processed.json()["line_items"]
    assert len(items) == 4
    assert {i["supplier"] for i in items} == {"Acme Corp", "Office Depot"}
    assert {i["invoice_number"] for i in items} == {"PO-2025-0101", "PO-2025-0102"}

    # Same visibility rules as an upload: another buyer sees it, finance doesn't.
    other_buyer = _register_and_login(client, "conn-buyer2@spend.com")
    assert client.get(f"/documents/{doc_id}", headers=other_buyer).status_code == 200
    finance = _register_and_login(client, "conn-finance2@spend.com", role_attempt="finance")
    assert client.get(f"/documents/{doc_id}", headers=finance).status_code == 404

    entry = db.query(AuditLog).filter(AuditLog.action == "connector_import", AuditLog.entity_id == doc_id).first()
    assert entry is not None and "mock_rest" in entry.details


def test_import_endpoint_validates_input(client: TestClient):
    buyer = _register_and_login(client, "conn-validate@spend.com")
    assert client.post("/connectors/import", json={"source": "sap"}, headers=buyer).status_code == 422
    assert client.post("/connectors/import", json={"source": "csv"}, headers=buyer).status_code == 422
    bad = client.post("/connectors/import", json={"source": "csv", "csv_text": "foo,bar\n1,2"}, headers=buyer)
    assert bad.status_code == 422 and "description" in bad.json()["detail"]
    good = client.post("/connectors/import", json={"source": "csv", "csv_text": _ERP_CSV}, headers=buyer)
    assert good.status_code == 201 and good.json()["rows_imported"] == 2 and good.json()["rows_skipped"] == 2
