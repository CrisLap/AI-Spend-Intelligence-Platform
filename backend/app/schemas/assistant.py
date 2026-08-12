from __future__ import annotations

from pydantic import BaseModel

from app.schemas.chat import ChatSource


class AssistantRequest(BaseModel):
    message: str
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
