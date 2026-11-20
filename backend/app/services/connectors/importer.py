from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.document import DocType, Document, DocumentStatus
from app.models.user import User
from app.services.audit_service import log_action
from app.services.connectors.base import Connector, rows_to_csv
from app.services.document_intelligence import save_upload


def import_from_connector(db: Session, user: User, connector: Connector) -> tuple[Document, int, int]:
    """Runs a connector and stores its normalized rows as a normal Document
    owned by `user` (so role-scoped visibility applies exactly as for an
    upload), then audit-logs the import. Returns (document, imported,
    skipped). Raises ValueError when the source yields nothing usable.

    The document is left in `processing` status: classification, anomaly and
    duplicate detection and vector indexing all happen in the existing
    POST /documents/{id}/process step, not here.
    """
    result = connector.fetch()
    if not result.rows:
        raise ValueError("The source returned no usable rows")

    content = rows_to_csv(result.rows)
    original_name = f"{connector.name}-import.csv"
    filename, file_path = save_upload(content, original_name)
    doc = Document(
        user_id=user.id,
        filename=filename,
        original_name=original_name,
        doc_type=DocType(connector.doc_type),
        file_path=file_path,
        file_size_bytes=len(content),
        status=DocumentStatus.processing,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log_action(
        db, user_id=user.id, action="connector_import", entity_type="document", entity_id=doc.id,
        details={"connector": connector.name, "rows": len(result.rows), "skipped": result.skipped},
    )
    return doc, len(result.rows), result.skipped
