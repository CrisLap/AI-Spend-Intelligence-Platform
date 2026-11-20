from __future__ import annotations

from app.services.connectors.base import MAX_ROWS, Connector, FetchResult, NormalizedRow

# What a typical ERP purchase-order endpoint (e.g. GET /api/purchase-orders)
# might return. Hard-coded so the connector runs with no network or
# credentials: it demonstrates the field mapping, not a live integration.
SAMPLE_ERP_PAYLOAD: dict = {
    "purchaseOrders": [
        {
            "poNumber": "PO-2025-0101",
            "orderDate": "2025-05-12",
            "vendor": {"id": "V-100", "name": "Acme Corp"},
            "lines": [
                {"itemDescription": "Server maintenance contract", "qty": 1, "unitPrice": 4200.0},
                {"itemDescription": "Rack mount kit", "qty": 4, "unitPrice": 89.5},
            ],
        },
        {
            "poNumber": "PO-2025-0102",
            "orderDate": "2025-05-14",
            "vendor": {"id": "V-210", "name": "Office Depot"},
            "lines": [
                {"itemDescription": "A4 paper 80g (box of 5 reams)", "qty": 20, "unitPrice": 17.9},
                {"itemDescription": "Toner cartridge HP 415A", "qty": 3, "unitPrice": 64.0},
            ],
        },
    ]
}


class MockRestConnector(Connector):
    """Maps an ERP REST payload (nested purchase orders with vendor and
    lines) onto NormalizedRow. A real connector would fetch the payload over
    HTTPS with stored credentials and reuse the same mapping; fetching is
    left out on purpose so the mock can't be turned into an SSRF vector."""

    name = "mock_rest"
    doc_type = "order"

    def __init__(self, payload: dict | None = None):
        self._payload = SAMPLE_ERP_PAYLOAD if payload is None else payload

    def fetch(self) -> FetchResult:
        rows: list[NormalizedRow] = []
        skipped = 0
        for order in self._payload.get("purchaseOrders", []):
            vendor = (order.get("vendor") or {}).get("name")
            for line in order.get("lines", []):
                try:
                    qty = float(line.get("qty", 1)) or 1.0
                    unit_price = float(line["unitPrice"])
                    description = str(line["itemDescription"]).strip()
                except (KeyError, TypeError, ValueError):
                    skipped += 1
                    continue
                if not description:
                    skipped += 1
                    continue
                if len(rows) >= MAX_ROWS:
                    raise ValueError(f"Payload has more than {MAX_ROWS} lines")
                rows.append(
                    NormalizedRow(
                        description=description[:500],
                        quantity=qty,
                        unit_price=unit_price,
                        total=round(qty * unit_price, 2),
                        supplier=(str(vendor)[:300] if vendor else None),
                        invoice_number=(str(order["poNumber"])[:100] if order.get("poNumber") else None),
                        invoice_date=(str(order["orderDate"])[:20] if order.get("orderDate") else None),
                    )
                )
        return FetchResult(rows=rows, skipped=skipped)
