from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    user_id: int
    filename: str
    original_name: str
    doc_type: str
    status: str
    page_count: int | None = None
    file_size_bytes: int | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LineItemOut(BaseModel):
    id: int
    document_id: int
    description: str
    quantity: float
    unit_price: float
    total: float
    supplier: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    category_unspsc: str | None = None
    category_label: str | None = None
    confidence: float | None = None
    classification_method: str | None = None
    is_anomaly: bool = False
    anomaly_reason: str | None = None
    anomaly_score: float | None = None

    model_config = {"from_attributes": True}


class DocumentWithItems(DocumentOut):
    line_items: list[LineItemOut] = []


class LineItemUpdate(BaseModel):
    category_label: str | None = None
    category_unspsc: str | None = None
    supplier: str | None = None
    description: str | None = None


class DuplicateGroupOut(BaseModel):
    id: int
    reason: str
    similarity: float
    items: list[LineItemOut] = []

    model_config = {"from_attributes": True}
