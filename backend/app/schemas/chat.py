from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: int | None = None


class ChatSource(BaseModel):
    text: str
    score: float
    source: str


class ChatResponse(BaseModel):
    reply: str
    sources: list[ChatSource]
    session_id: int


class ChatSessionOut(BaseModel):
    id: int
    summary: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources_json: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
