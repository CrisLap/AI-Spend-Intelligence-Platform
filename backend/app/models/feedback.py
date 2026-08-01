from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.core.database import Base


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(ForeignKey("users.id"), nullable=False)
    document_id = Column(ForeignKey("documents.id"), nullable=False)
    line_item_id = Column(ForeignKey("line_items.id"), nullable=True)
    original_category = Column(String(300), nullable=True)
    corrected_category = Column(String(300), nullable=False)
    original_method = Column(String(50), nullable=True)
    comment = Column(Text, nullable=True)
    is_used_for_training = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
