from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

# A connector can never hand the pipeline an unbounded batch.
MAX_ROWS = 5000

# Column order matches what document_intelligence.parse_tabular_items reads.
CSV_HEADERS = ["description", "quantity", "unit_price", "total", "supplier", "invoice_number", "invoice_date"]


@dataclass(frozen=True)
class NormalizedRow:
    """One spend line in the platform's own shape, whatever the source
    system called its fields."""

    description: str
    quantity: float
    unit_price: float
    total: float
    supplier: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None


@dataclass(frozen=True)
class FetchResult:
    rows: list[NormalizedRow]
    skipped: int = 0  # source records that could not be normalized


class Connector(ABC):
    """A source of spend lines (an ERP, a CSV export, a REST API).

    A connector only *fetches and normalizes*; it never touches the
    database. Persisting, scoping to the importing user, audit logging and
    all later processing (classification, anomaly/duplicate detection,
    embeddings) are done by the existing document pipeline, so a connector
    can't bypass any of it.
    """

    name: ClassVar[str]
    doc_type: ClassVar[str] = "other"  # invoice | order | contract | other

    @abstractmethod
    def fetch(self) -> FetchResult: ...


def rows_to_csv(rows: list[NormalizedRow]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADERS)
    for r in rows:
        writer.writerow([getattr(r, h) if getattr(r, h) is not None else "" for h in CSV_HEADERS])
    return buf.getvalue().encode("utf-8")
