from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.document import DocumentOut


class ConnectorImportRequest(BaseModel):
    source: Literal["csv", "mock_rest"]
    # Only for source="csv". Capped so a request can't buffer an unbounded
    # body; the service additionally enforces the row cap.
    csv_text: str | None = Field(default=None, max_length=5_000_000)


class ConnectorImportOut(BaseModel):
    document: DocumentOut
    rows_imported: int
    rows_skipped: int
    # The imported document still has to go through POST /documents/{id}/process
    # (classification, anomalies, duplicates, indexing), same as an upload.
    next_step: str = "POST /documents/{id}/process"
