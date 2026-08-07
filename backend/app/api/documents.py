from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.document import DocType, Document, DocumentStatus, LineItem, LineItemGroup, LineItemGroupItem
from app.models.feedback import Feedback
from app.models.user import User
from app.schemas.document import DocumentOut, DocumentWithItems, LineItemOut
from app.services.ai import embed_text
from app.services.anomalies import detect_anomalies
from app.services.audit_service import log_action
from app.services.classifier import classify_batch
from app.services.document_intelligence import extract_metadata, extract_raw_text, parse_items, save_upload
from app.services.duplicates import find_duplicates
from app.services.vector_store import delete_line_items, upsert_line_item

router = APIRouter(prefix="/documents", tags=["documents"])


def _clear_document_children(db: Session, document_id: int) -> list[int]:
    """Delete everything that depends on this document's line items
    (duplicate groups, feedback) and the line items themselves.

    Used both before re-processing a document (so re-running /process
    doesn't pile up duplicate line items on top of the old ones) and before
    deleting a document outright (so the delete doesn't violate foreign key
    constraints on Postgres/Neon - SQLite doesn't enforce these by default,
    which is why this went unnoticed in local testing).

    Returns the deleted line item ids, so the caller can also clear the
    matching vectors from Qdrant.
    """
    item_ids = [i.id for i in db.query(LineItem.id).filter(LineItem.document_id == document_id).all()]
    group_ids = []
    if item_ids:
        group_ids = [
            g.group_id
            for g in db.query(LineItemGroupItem.group_id)
            .filter(LineItemGroupItem.line_item_id.in_(item_ids))
            .distinct()
        ]
    db.query(Feedback).filter(Feedback.document_id == document_id).delete(synchronize_session=False)
    if item_ids:
        db.query(LineItemGroupItem).filter(
            LineItemGroupItem.line_item_id.in_(item_ids)
        ).delete(synchronize_session=False)
    if group_ids:
        db.query(LineItemGroup).filter(LineItemGroup.id.in_(group_ids)).delete(synchronize_session=False)
    db.query(LineItem).filter(LineItem.document_id == document_id).delete(synchronize_session=False)
    db.commit()
    return item_ids

ALLOWED_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}


@router.post("/upload", response_model=DocumentOut, status_code=201)
def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Query("auto", description="invoice, order, contract, auto"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    original_name = file.filename or "unknown"
    suffix = "." + original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = file.file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_mb}MB upload limit",
        )

    filename, file_path = save_upload(content, file.filename or "unknown")
    ext = (file.filename or "").lower()
    detected_type = DocType.other
    if "invoice" in ext or doc_type == "invoice":
        detected_type = DocType.invoice
    elif "order" in ext or doc_type == "order":
        detected_type = DocType.order
    elif doc_type == "contract":
        detected_type = DocType.contract

    doc = Document(
        user_id=user.id,
        filename=filename,
        original_name=file.filename or "unknown",
        doc_type=detected_type,
        file_path=file_path,
        file_size_bytes=len(content),
        status=DocumentStatus.processing,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log_action(
        db, user_id=user.id, action="upload_document", entity_type="document", entity_id=doc.id,
        details={"filename": doc.original_name, "doc_type": doc.doc_type.value if doc.doc_type else None},
    )
    return DocumentOut.model_validate(doc)


@router.post("/{doc_id}/process", response_model=DocumentWithItems)
def process_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        raw_text = extract_raw_text(doc.file_path, doc.filename)
        doc.raw_text = raw_text

        # Re-processing an already-processed document must replace its line
        # items, not pile new ones on top of the old ones.
        old_item_ids = _clear_document_children(db, doc.id)
        if old_item_ids:
            delete_line_items(old_item_ids)

        metadata = extract_metadata(raw_text)
        parsed = parse_items(raw_text, doc.doc_type.value if doc.doc_type else None)

        items = []
        for p in parsed:
            item = LineItem(
                document_id=doc.id,
                description=p.get("description", ""),
                quantity=float(p.get("quantity", 1)),
                unit_price=float(p.get("unit_price", 0)),
                total=float(p.get("total", 0)),
                supplier=p.get("supplier") or metadata.get("supplier"),
                invoice_number=p.get("invoice_number") or metadata.get("invoice_number"),
                invoice_date=p.get("invoice_date") or metadata.get("invoice_date"),
            )
            db.add(item)
            items.append(item)

        db.commit()
        for item in items:
            db.refresh(item)

        descriptions = [i.description for i in items if i.description]
        if descriptions:
            classifications = classify_batch(descriptions)
            for item, cls in zip(items, classifications):
                item.category_label = cls["category"]
                item.category_unspsc = cls.get("unspsc", "")
                item.confidence = cls["confidence"]
                item.classification_method = cls["method"]

            anomalies = detect_anomalies(items, db=db)
            for item, anom in zip(items, anomalies):
                item.is_anomaly = anom["is_anomaly"]
                item.anomaly_reason = anom["reason"]
                item.anomaly_score = anom["zscore"]

            for item in items:
                if item.description:
                    upsert_line_item(
                        item.id,
                        embed_text(item.description),
                        payload={
                            "document_id": doc.id,
                            "user_id": doc.user_id,
                            "description": item.description,
                            "supplier": item.supplier,
                            "total": item.total,
                            "category": item.category_label,
                            "source": doc.original_name,
                        },
                    )

            dup_groups = find_duplicates(items, threshold=settings.duplicate_similarity_threshold)
            if dup_groups:
                from app.models.document import LineItemGroup, LineItemGroupItem
                for g in dup_groups:
                    grp = LineItemGroup(reason=g["reason"], similarity=g["similarity"])
                    db.add(grp)
                    db.commit()
                    for gi in g["items"]:
                        li = next((it for it in items if it.id == gi["id"]), None)
                        if li:
                            db.add(LineItemGroupItem(group_id=grp.id, line_item_id=li.id))
                    db.commit()

        doc.status = DocumentStatus.classified
        db.commit()
        db.refresh(doc)
        db_items = db.query(LineItem).filter(LineItem.document_id == doc.id).all()
        result = DocumentWithItems(
            **{c.name: getattr(doc, c.name) for c in doc.__table__.columns},
            line_items=[LineItemOut.model_validate(i) for i in db_items],
        )
        return result
    except Exception as e:
        doc.status = DocumentStatus.failed
        doc.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[DocumentOut])
def list_documents(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    docs = db.query(Document).filter(Document.user_id == user.id).order_by(
        Document.created_at.desc()
    ).offset(skip).limit(limit).all()
    return [DocumentOut.model_validate(d) for d in docs]


@router.get("/{doc_id}", response_model=DocumentWithItems)
def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    items = db.query(LineItem).filter(LineItem.document_id == doc.id).all()
    return DocumentWithItems(
        **{c.name: getattr(doc, c.name) for c in doc.__table__.columns},
        line_items=[LineItemOut.model_validate(i) for i in items],
    )


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    item_ids = _clear_document_children(db, doc.id)
    original_name = doc.original_name
    db.delete(doc)
    db.commit()
    delete_line_items(item_ids)
    log_action(
        db, user_id=user.id, action="delete_document", entity_type="document", entity_id=doc_id,
        details={"filename": original_name},
    )
