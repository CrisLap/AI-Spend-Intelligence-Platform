from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.chat import ChatSource


class AssistantRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: int | None = None


class AssistantChatResult(BaseModel):
    reply: str
    sources: list[ChatSource]
    session_id: int


class AssistantSuggestion(BaseModel):
    agent_type: str
    goal: str


class AssistantResponse(BaseModel):
    intent: str
    method: str
    confidence: float
    chat: AssistantChatResult | None = None
    suggestion: AssistantSuggestion | None = None
