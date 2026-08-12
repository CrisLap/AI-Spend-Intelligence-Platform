from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    goal: str = Field(default="Trova opportunità di risparmio", max_length=500)


class AgentStepOut(BaseModel):
    index: int
    thought: str | None = None
    tool: str | None = None
    tool_input: str | None = None
    observation: str | None = None


class RecommendationOut(BaseModel):
    title: str
    reason: str
    supplier: str | None = None
    category: str | None = None
    estimated_saving: float | None = None
    currency: str = "EUR"
    confidence: str
    evidence: list[str] = []


class AgentRunOut(BaseModel):
    id: int
    goal: str
    summary: str
    steps: list[AgentStepOut]
    recommendations: list[RecommendationOut]
    created_at: datetime
