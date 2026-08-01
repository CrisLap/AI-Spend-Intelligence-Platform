from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FeedbackCreate(BaseModel):
    document_id: int
    line_item_id: int | None = None
    original_category: str | None = None
    corrected_category: str
    comment: str | None = None


class FeedbackOut(BaseModel):
    id: int
    user_id: int
    document_id: int
    line_item_id: int | None = None
    original_category: str | None = None
    corrected_category: str
    original_method: str | None = None
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
