from __future__ import annotations

import csv
import io
import re

from app.services.connectors.base import MAX_ROWS, Connector, FetchResult, NormalizedRow
from app.services.document_intelligence import TABULAR_ALIASES, _to_float


def _number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return _to_float(value)
    except ValueError:
        return None


def _text(value: str | None, limit: int) -> str | None:
    return (value or "").strip()[:limit] or None


class CsvConnector(Connector):
    """Normalizes a CSV export (any of the header aliases in
    document_intelligence.TABULAR_ALIASES, e.g. Vendor/Qty/PO Number)."""

    name = "csv"
    doc_type = "invoice"

    def __init__(self, csv_text: str):
        self._csv_text = csv_text

    def fetch(self) -> FetchResult:
        reader = csv.DictReader(io.StringIO(self._csv_text))
        columns: dict[str, str] = {}
        for header in reader.fieldnames or []:
            key = re.sub(r"[\s-]+", "_", header.strip().lower())
            for canonical, aliases in TABULAR_ALIASES.items():
                if key in aliases and canonical not in columns:
                    columns[canonical] = header
        if "description" not in columns or not ({"total", "unit_price"} & columns.keys()):
            raise ValueError("CSV needs a description column and a total or unit price column")

        rows: list[NormalizedRow] = []
        skipped = 0
        for record in reader:
            if len(rows) >= MAX_ROWS:
                raise ValueError(f"CSV has more than {MAX_ROWS} rows")
            description = _text(record.get(columns["description"]), 500)
            quantity = _number(record.get(columns.get("quantity", ""))) or 1.0
            unit_price = _number(record.get(columns.get("unit_price", "")))
            total = _number(record.get(columns.get("total", "")))
            if total is None and unit_price is not None:
                total = round(quantity * unit_price, 2)
            if not description or total is None:
                skipped += 1
                continue
            if unit_price is None:
                unit_price = round(total / quantity, 2)
            rows.append(
                NormalizedRow(
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    total=total,
                    supplier=_text(record.get(columns.get("supplier", "")), 300),
                    invoice_number=_text(record.get(columns.get("invoice_number", "")), 100),
                    invoice_date=_text(record.get(columns.get("invoice_date", "")), 20),
                )
            )
        return FetchResult(rows=rows, skipped=skipped)
