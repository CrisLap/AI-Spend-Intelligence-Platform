from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.connector import ConnectorImportOut, ConnectorImportRequest
from app.schemas.document import DocumentOut
from app.services.connectors import AVAILABLE_CONNECTORS, build_connector
from app.services.connectors.importer import import_from_connector

router = APIRouter(prefix="/connectors", tags=["connectors"], dependencies=[Depends(get_current_user)])


@router.get("")
def list_connectors() -> list[str]:
    return list(AVAILABLE_CONNECTORS)


@router.post("/import", response_model=ConnectorImportOut, status_code=201)
@limiter.limit("20/minute")
def import_spend(
    request: Request,
    payload: ConnectorImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "buyer")),
):
    try:
        connector = build_connector(payload.source, payload.csv_text)
        doc, imported, skipped = import_from_connector(db, user, connector)
    except ValueError as e:
        # ValueError messages here are our own validation texts (row cap,
        # missing columns, empty source), safe to show to the caller.
        raise HTTPException(status_code=422, detail=str(e)) from e
    return ConnectorImportOut(document=DocumentOut.model_validate(doc), rows_imported=imported, rows_skipped=skipped)
