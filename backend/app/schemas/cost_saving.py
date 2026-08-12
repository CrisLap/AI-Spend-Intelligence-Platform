from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    goal: str = Field(default="Trova opportunità di risparmio", max_length=500)
    agent_type: str = Field(default="cost_saving", max_length=50)


class AgentStepOut(BaseModel):
    index: int
    thought: str | None = None
    tool: str | None = None
    tool_input: str | None = None
    observation: str | None = None
    mode: str | None = None


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
    agent_type: str
    goal: str
    summary: str
    steps: list[AgentStepOut]
    recommendations: list[RecommendationOut]
    created_at: datetime
