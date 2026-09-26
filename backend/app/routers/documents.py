"""Document API — upload, download (hash-verified), list.

- POST /documents (multipart): validated, hashed, stored, deduped per tenant.
  Returns the row; re-upload of identical bytes returns the existing row.
- GET /documents: premium-grid list with resource filter.
- GET /documents/{id}/download: streams bytes after re-verifying SHA-256;
  tampered files => 409 and quarantine (never silent).
- Audit: DOCUMENT_UPLOADED on every accepted store.
"""
from __future__ import annotations

import os
from collections.abc import Generator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.document import DOC_STATUSES, Document
from ..services.audit import record_event
from ..services.document import (
    DocumentError,
    check_size,
    sha256_hex,
    sniff_kind,
    storage_path,
    validate_filename,
    verify_bytes,
)

router = APIRouter(tags=["documents"])
WRITE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer", "Category Manager", "Supplier Manager"}


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _write(actor: Actor) -> None:
    if not set(actor.roles or ()) & WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for document write")


@router.post("/documents", status_code=201)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    resource: str = Form(default=""),
    resource_id: str = Form(default=""),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(db_for_actor),
) -> dict:
    _write(actor)
    try:
        filename = validate_filename(file.filename or "")
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    data = await file.read()
    try:
        check_size(len(data))
    except DocumentError as exc:
        raise HTTPException(status_code=422 if exc.code != "DOC_TOO_LARGE" else 413,
                            detail={"code": exc.code, "message": exc.message}) from exc
    kind = sniff_kind(data[:16], filename)
    if kind == "unknown":
        raise HTTPException(status_code=422, detail={"code": "DOC_TYPE_UNVERIFIED", "message": "Content does not match an allowed type"})
    digest = sha256_hex(data)
    existing = db.execute(select(Document).where(Document.tenant_id == actor.tenant_id, Document.sha256 == digest)).scalar_one_or_none()
    if existing is not None:
        record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_UPLOADED", resource="document",
                     resource_id=existing.id, after={"filename": filename, "sha256": digest, "deduped": True}, source="api",
                     ip=request.client.host if request.client else "", created_by=actor.sub)
        db.commit()
        return envelope({"id": existing.id, "deduped": True, "sha256": digest}, None, getattr(request.state, "request_id", ""))
    dest = storage_path(actor.tenant_id, digest)
    if not dest.exists():
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    row = Document(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, filename=filename,
                   content_type=file.content_type or "application/octet-stream", size_bytes=len(data), sha256=digest,
                   storage_key=str(dest), status="uploaded", resource=resource.strip()[:64], resource_id=resource_id.strip()[:36])
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.execute(select(Document).where(Document.tenant_id == actor.tenant_id, Document.sha256 == digest)).scalar_one_or_none()
        return envelope({"id": existing.id if existing else "", "deduped": True, "sha256": digest}, None, getattr(request.state, "request_id", ""))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_UPLOADED", resource="document",
                 resource_id=row.id, after={"filename": filename, "sha256": digest, "bytes": len(data)}, source="api",
                 ip=request.client.host if request.client else "", created_by=actor.sub)
    db.commit()
    db.refresh(row)
    return envelope({"id": row.id, "deduped": False, "sha256": digest}, None, getattr(request.state, "request_id", ""))


@router.get("/documents")
def list_docs(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
              limit: int = Query(default=25, ge=1, le=100), cursor: str = Query(default=""),
              search: str = Query(default=""), resource: str = Query(default="")) -> dict:
    stmt = select(Document).where(Document.tenant_id == actor.tenant_id)
    if resource:
        stmt = stmt.where(Document.resource == resource)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Document.filename.ilike(like), Document.sha256.ilike(like)))
    if cursor:
        cur = db.execute(select(Document).where(Document.tenant_id == actor.tenant_id, Document.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(Document.created_at < cur.created_at,
                              ((Document.created_at == cur.created_at) & (Document.id < cursor))))
    stmt = stmt.order_by(desc(Document.created_at), desc(Document.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more, rows = len(rows) > limit, rows[:limit]
    data = [{"id": r.id, "filename": r.filename, "sizeBytes": r.size_bytes, "sha256": r.sha256,
             "status": r.status, "resource": r.resource, "createdAt": r.created_at.isoformat() if r.created_at else ""} for r in rows]
    return envelope(data, {"limit": limit, "nextCursor": rows[-1].id if has_more and rows else "", "hasMore": has_more}, getattr(request.state, "request_id", ""))


@router.get("/documents/{doc_id}/download")
def download(doc_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> FileResponse:
    from pathlib import Path

    row = db.execute(select(Document).where(Document.tenant_id == actor.tenant_id, Document.id == doc_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    path = Path(row.storage_key)
    if not path.exists() or not verify_bytes(path, row.sha256):
        row.status = "quarantined"
        record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_QUARANTINED", resource="document",
                     resource_id=row.id, after={"reason": "integrity-check-failed"}, source="system", created_by=actor.sub)
        db.commit()
        raise HTTPException(status_code=409, detail="Stored bytes failed integrity check — quarantined")
    safe = row.filename.replace('"', "")
    return FileResponse(path, media_type=row.content_type, filename=safe, headers={"X-SHA256": row.sha256})


DOC_STATUSES_EXPORT = sorted(DOC_STATUSES)
