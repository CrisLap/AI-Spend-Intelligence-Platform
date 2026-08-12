from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from app.core.database import Base


class AgentRun(Base):
    """A single agent invocation - Cost Saving, Forecast, or Contract Risk
    (see agent_type; app/services/cost_saving_agent.py's AGENT_TYPES) - the
    goal it was given, the ReAct trace it produced (steps_json) and the
    structured recommendations the Recommendation Engine derived from real
    spend data (recommendations_json). These three agent types share this
    one table/endpoint/frontend page (parametrized by agent_type) rather
    than each getting its own REST/UI, per the project's Fase 2 plan.
    Persisted so past runs show up as history in the UI and are covered by
    the same audit trail as other actions."""

    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(ForeignKey("users.id"), nullable=False)
    agent_type = Column(String(50), nullable=False, server_default="cost_saving")
    goal = Column(Text, nullable=False)
    steps_json = Column(Text, nullable=True)
    recommendations_json = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
