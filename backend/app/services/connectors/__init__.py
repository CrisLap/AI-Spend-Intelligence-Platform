"""Spend-data connectors: fetch + normalize rows from an external source;
persistence and processing stay in the existing document pipeline (see
importer.py)."""
from __future__ import annotations

from app.services.connectors.base import Connector, FetchResult, NormalizedRow
from app.services.connectors.csv_connector import CsvConnector
from app.services.connectors.mock_rest import MockRestConnector

AVAILABLE_CONNECTORS = ("csv", "mock_rest")


def build_connector(source: str, csv_text: str | None = None) -> Connector:
    if source == "csv":
        if not csv_text or not csv_text.strip():
            raise ValueError("The csv connector needs csv_text")
        return CsvConnector(csv_text)
    if source == "mock_rest":
        return MockRestConnector()
    raise ValueError(f"Unknown connector '{source}'")


__all__ = [
    "AVAILABLE_CONNECTORS",
    "Connector",
    "CsvConnector",
    "FetchResult",
    "MockRestConnector",
    "NormalizedRow",
    "build_connector",
]
