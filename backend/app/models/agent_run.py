from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, func

from app.core.database import Base


class AgentRun(Base):
    """A single Cost Saving Agent invocation: the goal it was given, the
    ReAct trace it produced (steps_json) and the structured recommendations
    the Recommendation Engine derived from real spend data
    (recommendations_json) - persisted so past runs show up as history in
    the UI and are covered by the same audit trail as other actions."""

    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(ForeignKey("users.id"), nullable=False)
    goal = Column(Text, nullable=False)
    steps_json = Column(Text, nullable=True)
    recommendations_json = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
