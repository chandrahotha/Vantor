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
from sqlalchemy import and_, desc, or_, select
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
    # `resource`/`resource_id` are a polymorphic pointer (the target table comes
    # from `resource`), so there is no parent to validate against. What we can
    # refuse is a value that does not fit: the old code truncated to the column
    # width, which silently stored an id that matches no record at all.
    if len(resource_id.strip()) > 36:
        raise HTTPException(status_code=422, detail={
            "code": "REFERENCE_TOO_LONG",
            "message": "resource_id must be at most 36 characters",
            "details": {"length": len(resource_id.strip())},
        })
    if len(resource.strip()) > 64:
        raise HTTPException(status_code=422, detail={
            "code": "REFERENCE_TOO_LONG",
            "message": "resource must be at most 64 characters",
            "details": {"length": len(resource.strip())},
        })
    row = Document(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, filename=filename,
                   content_type=file.content_type or "application/octet-stream", size_bytes=len(data), sha256=digest,
                   storage_key=str(dest), status="uploaded", resource=resource.strip(), resource_id=resource_id.strip())
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


@router.post("/documents/{doc_id}/extract")
def extract_doc(doc_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Extract text + chunk into DocumentChunk rows. Scanned/unreadable bytes
    quarantine with an explicit reason (never fake-extracted). Idempotent per
    document: re-extract replaces prior chunks.

    Role-gated: extraction mutates document status and rewrites chunk rows, so
    it requires the same write roles as upload. A 200 with `quarantined: true`
    is a real outcome, not a success — hence 200, not 201.
    """
    from pathlib import Path

    from ..models.document import DocumentChunk
    from ..services.embeddings import EmbeddingError, embed
    from ..services.extract import ExtractError, chunk_text, extract

    _write(actor)
    row = db.execute(select(Document).where(Document.tenant_id == actor.tenant_id, Document.id == doc_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    path = Path(row.storage_key)
    if not path.exists() or not verify_bytes(path, row.sha256):
        raise HTTPException(status_code=409, detail="Stored bytes failed integrity check")
    try:
        result = extract(row.filename, path.read_bytes())
    except ExtractError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    if result.scanned:
        row.status = "quarantined"
        record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_QUARANTINED", resource="document",
                     resource_id=row.id, after={"reason": f"no text layer ({result.kind})"}, source="system", created_by=actor.sub)
        db.commit()
        return envelope({"chunks": 0, "quarantined": True, "reason": "no text layer"}, None, getattr(request.state, "request_id", ""))
    try:
        chunks = chunk_text(result.text)
    except ExtractError as exc:
        raise HTTPException(status_code=500, detail={"code": exc.code, "message": exc.message}) from exc

    for old in db.execute(select(DocumentChunk).where(DocumentChunk.tenant_id == actor.tenant_id, DocumentChunk.document_id == doc_id)).scalars():
        db.delete(old)

    embedded = 0
    provider_failed = False
    for i, text in enumerate(chunks):
        chunk = DocumentChunk(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                              document_id=doc_id, chunk_no=i, text=text, embedding={})
        try:
            vec = embed(text)
            if vec is not None:
                chunk.embedding = vec
                embedded += 1
        except EmbeddingError:
            provider_failed = True
        db.add(chunk)
    row.status = "ready"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_EXTRACTED", resource="document",
                 resource_id=row.id, after={"chunks": len(chunks), "embedded": embedded, "kind": result.kind}, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"chunks": len(chunks), "embedded": embedded, "embeddingProviderFailed": provider_failed,
                     "quarantined": False, "kind": result.kind}, None, getattr(request.state, "request_id", ""))


@router.get("/documents/search")
def search_docs(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
                q: str = Query(default="", min_length=2, max_length=200)) -> dict:
    """Keyword + optional semantic ranking over extracted chunks.

    Keyword stage: ILIKE substring match (works on SQLite and Postgres). Ranking
    stage: if the embedding provider has written vectors, cosine score re-orders
    those candidates; otherwise the keyword order stands and `mode` says so.
    Chunks without vectors are never ranked as if they matched.

    Chunks are joined to their parent document so a QUARANTINED document is not
    searchable. It was not joined before, and the two quarantine paths return
    before the chunk delete, so text from a document explicitly held for review
    kept surfacing in search results.
    """
    from ..models.document import DocumentChunk
    from ..services.embeddings import rank

    like = f"%{q.strip()}%"
    rows = list(db.execute(
        select(DocumentChunk, Document.status).join(
            Document, and_(Document.id == DocumentChunk.document_id, Document.tenant_id == actor.tenant_id))
        .where(DocumentChunk.tenant_id == actor.tenant_id,
               Document.status != "quarantined",
               DocumentChunk.text.ilike(like))
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_no).limit(50)).all())

    candidates = [{"id": h.id, "document_id": h.document_id, "chunk_no": h.chunk_no,
                   "text": h.text[:280], "embedding": h.embedding} for h, _status in rows]
    ranked, mode = rank(q, candidates)
    out = [{"documentId": r["document_id"], "chunkNo": r["chunk_no"], "excerpt": r["text"]} for r in ranked[:25]]
    return envelope(out, {"count": len(out), "mode": mode}, getattr(request.state, "request_id", ""))


DOC_STATUSES_EXPORT = sorted(DOC_STATUSES)
