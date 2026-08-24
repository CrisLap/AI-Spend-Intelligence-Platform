import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func

from app.core.database import Base


class DocType(enum.Enum):
    invoice = "invoice"
    order = "order"
    contract = "contract"
    other = "other"


class DocumentStatus(enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    parsed = "parsed"
    failed = "failed"
    classified = "classified"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(ForeignKey("users.id"), nullable=False)
    filename = Column(String(500), nullable=False)
    original_name = Column(String(500), nullable=False)
    doc_type = Column(Enum(DocType), default=DocType.other)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.uploaded)
    file_path = Column(String(1000), nullable=True)
    raw_text = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LineItem(Base):
    __tablename__ = "line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(ForeignKey("documents.id"), nullable=False)
    description = Column(Text, nullable=False)
    quantity = Column(Float, default=1.0)
    unit_price = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    supplier = Column(String(300), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    invoice_date = Column(String(20), nullable=True)
    category_unspsc = Column(String(20), nullable=True)
    category_label = Column(String(300), nullable=True)
    confidence = Column(Float, nullable=True)
    classification_method = Column(String(50), nullable=True)
    is_anomaly = Column(Boolean, default=False)
    anomaly_reason = Column(Text, nullable=True)
    anomaly_score = Column(Float, nullable=True)
    anomaly_resolved = Column(Boolean, default=False, nullable=False, server_default="false")
    embedding_cache = Column(Text, nullable=True)  # JSON-encoded float list, lazily populated by search
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LineItemGroup(Base):
    __tablename__ = "line_item_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reason = Column(String(100), nullable=False)
    similarity = Column(Float, default=1.0)
    resolved = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LineItemGroupItem(Base):
    __tablename__ = "line_item_group_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(ForeignKey("line_item_groups.id"), nullable=False)
    line_item_id = Column(ForeignKey("line_items.id"), nullable=False)


class ContractClause(Base):
    """A chunk of a contract document's full text, indexed separately from
    LineItem so contract-level semantic search (renewal clauses, penalties,
    exclusivity terms) isn't limited to the line-item granularity the rest
    of the RAG pipeline uses."""

    __tablename__ = "contract_clauses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    embedding_cache = Column(Text, nullable=True)  # JSON-encoded float list, lazily populated by search
    created_at = Column(DateTime(timezone=True), server_default=func.now())
