"""Document API — upload, download (hash-verified), list.

- POST /documents (multipart): validated, hashed, stored, deduped per tenant.
  Returns the row; re-upload of identical bytes returns the existing row.
- GET /documents: premium-grid list with resource filter.
- GET /documents/{id}/download: streams bytes after re-verifying SHA-256;
  tampered files => 409 and quarantine (never silent).
- Audit: DOCUMENT_UPLOADED on every accepted store.
"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.document import DOC_STATUSES, Document
from ..services.audit import record_event
from ..services.document import (
    DocumentError,
    get_storage,
    ingest,
    sha256_hex,
    storage_key,
    validate_filename,
)
from ..services.refs import require_ref

router = APIRouter(tags=["documents"])
WRITE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer", "Category Manager", "Supplier Manager"}


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _write(actor: Actor) -> None:
    if not set(actor.roles or ()) & WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for document write")


#: VNT-013. `documents.resource`/`resource_id` are a polymorphic pointer, and the
#: old code validated only the *length* of `resource_id` — with a comment
#: explaining that there was no parent to validate against. There is: a `resource`
#: name maps to exactly one model, so the reference is checkable. The registry is
#: the mapping, which turns "we cannot validate this" into "we can validate every
#: value of it". A document attached to a `purchase_order` id from another tenant
#: used to be accepted with 201.
RESOURCE_MODELS: dict[str, tuple[type, str]] = {}


def _resource_model(resource: str):  # type: ignore[no-untyped-def]
    """Resolve `resource` to its model, or None when the name is not known."""
    if not RESOURCE_MODELS:
        from ..models.contract import Contract
        from ..models.purchase import Invoice, PurchaseOrder, Requisition
        from ..models.sourcing import Rfq
        from ..models.supplier import Supplier

        RESOURCE_MODELS.update({
            "contract": (Contract, "UNKNOWN_CONTRACT"),
            "invoice": (Invoice, "UNKNOWN_INVOICE"),
            "purchase_order": (PurchaseOrder, "UNKNOWN_PURCHASE_ORDER"),
            "requisition": (Requisition, "UNKNOWN_REQUISITION"),
            "rfq": (Rfq, "UNKNOWN_RFQ"),
            "supplier": (Supplier, "UNKNOWN_SUPPLIER"),
        })
    return RESOURCE_MODELS.get(resource)


def _resolve_resource(db: Session, tenant_id: str, resource: str, resource_id: str) -> tuple[str, str | None]:
    """Validate a polymorphic reference. Returns `(resource, resource_id)`.

    Empty is legitimate: a document may be uploaded before the record it belongs
    to exists, and the workkit's DOCUMENT.md treats that as a valid state. But if
    a resource *name* is given, it must be one this build knows, and the id must
    point at a real record in this tenant.
    """
    name = (resource or "").strip()
    ref = (resource_id or "").strip()
    if not name and not ref:
        return "", None
    if bool(name) != bool(ref):
        raise DocumentError(
            "REFERENCE_INCOMPLETE",
            "resource and resource_id must be given together",
            {"resource": name, "resourceId": ref})
    model = _resource_model(name)
    if model is None:
        raise DocumentError(
            "REFERENCE_UNKNOWN_RESOURCE",
            f"resource {name!r} is not an attachable type",
            {"resource": name, "attachable": sorted(RESOURCE_MODELS)})
    # `require_ref` is the same validator every other link uses; it checks
    # existence *within the tenant*, which is the property that matters.
    require_ref(db, model[0], tenant_id, ref, field="resource_id", code=model[1])
    return name, ref


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
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message,
                                                      "details": exc.details}) from exc
    # VNT-010. `ingest` refuses on a declared Content-Length over the cap before
    # reading a byte, then re-checks the running total after every chunk, so the
    # peak allocation is bounded by the cap rather than by the request.
    try:
        ingested = await run_in_threadpool(
            ingest, file.file, filename=filename,
            declared_mime=file.content_type or "")
    except DocumentError as exc:
        raise HTTPException(
            status_code=413 if exc.code == "DOC_TOO_LARGE" else 422,
            detail={"code": exc.code, "message": exc.message, "details": exc.details}) from exc

    data, digest = ingested.data, ingested.digest
    existing = db.execute(select(Document).where(Document.tenant_id == actor.tenant_id, Document.sha256 == digest)).scalar_one_or_none()
    if existing is not None:
        record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_UPLOADED", resource="document",
                     resource_id=existing.id, after={"filename": filename, "sha256": digest, "deduped": True}, source="api",
                     ip=request.client.host if request.client else "", created_by=actor.sub)
        db.commit()
        return envelope({"id": existing.id, "deduped": True, "sha256": digest, "kind": ingested.kind},
                        None, getattr(request.state, "request_id", ""))
    try:
        resource_name, resource_ref = _resolve_resource(db, actor.tenant_id, resource, resource_id)
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message,
                                                      "details": exc.details}) from exc

    # VNT-009. Bytes go through the configured storage driver, not a fixed local
    # path. A storage failure is reported, not swallowed: the previous write
    # returned 201 and audited a success for bytes that a redeploy destroyed.
    key = storage_key(actor.tenant_id, digest)
    try:
        storage = get_storage()
        if not storage.exists(key):
            await run_in_threadpool(storage.write, key, data)
    except DocumentError:
        raise
    except Exception as exc:
        record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_STORAGE_FAILED",
                     resource="document", after={"sha256": digest, "driver": "unknown"},
                     reason=f"{type(exc).__name__}", source="api", created_by=actor.sub)
        db.commit()
        raise HTTPException(status_code=503, detail={
            "code": "DOC_STORAGE_UNAVAILABLE",
            "message": "Document storage is not available; the upload was not stored",
            "details": {"error": type(exc).__name__}}) from exc

    row = Document(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, filename=filename,
                   content_type=file.content_type or "application/octet-stream", size_bytes=ingested.size, sha256=digest,
                   storage_key=key, status="uploaded", resource=resource_name, resource_id=resource_ref or "")
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.execute(select(Document).where(Document.tenant_id == actor.tenant_id, Document.sha256 == digest)).scalar_one_or_none()
        return envelope({"id": existing.id if existing else "", "deduped": True, "sha256": digest}, None, getattr(request.state, "request_id", ""))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_UPLOADED", resource="document",
                 resource_id=row.id, after={"filename": filename, "sha256": digest, "bytes": ingested.size,
                                            "kind": ingested.kind}, source="api",
                 ip=request.client.host if request.client else "", created_by=actor.sub)
    db.commit()
    db.refresh(row)
    return envelope({"id": row.id, "deduped": False, "sha256": digest, "kind": ingested.kind},
                    None, getattr(request.state, "request_id", ""))


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
def download(doc_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> Response:
    """Serve the stored bytes, re-verifying the hash on every read.

    VNT-009: the bytes are fetched through the storage driver rather than by
    treating `storage_key` as a filesystem path, so the same code serves a local
    volume and an object store. The integrity re-check is kept — it is what turns
    silent corruption into an explicit quarantine instead of a wrong document.
    """
    row = db.execute(select(Document).where(Document.tenant_id == actor.tenant_id, Document.id == doc_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        payload = get_storage().read(row.storage_key)
    except Exception as exc:
        record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_QUARANTINED",
                     resource="document", resource_id=row.id,
                     after={"reason": "storage-unreadable"}, source="system", created_by=actor.sub)
        row.status = "quarantined"
        db.commit()
        raise HTTPException(status_code=503, detail={
            "code": "DOC_STORAGE_UNAVAILABLE",
            "message": "Document bytes could not be read",
            "details": {"error": type(exc).__name__}}) from exc
    if sha256_hex(payload) != row.sha256:
        row.status = "quarantined"
        record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_QUARANTINED", resource="document",
                     resource_id=row.id, after={"reason": "integrity-check-failed"}, source="system", created_by=actor.sub)
        db.commit()
        raise HTTPException(status_code=409, detail="Stored bytes failed integrity check — quarantined")
    safe = row.filename.replace('"', "")
    return Response(content=payload, media_type=row.content_type, headers={
        "Content-Disposition": f'attachment; filename="{safe}"',
        "X-SHA256": row.sha256,
        "X-Content-Type-Options": "nosniff",
    })


@router.post("/documents/{doc_id}/extract")
def extract_doc(doc_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Extract text + chunk into DocumentChunk rows. Scanned/unreadable bytes
    quarantine with an explicit reason (never fake-extracted). Idempotent per
    document: re-extract replaces prior chunks.

    Role-gated: extraction mutates document status and rewrites chunk rows, so
    it requires the same write roles as upload. A 200 with `quarantined: true`
    is a real outcome, not a success — hence 200, not 201.
    """
    from ..models.document import DocumentChunk
    from ..services.embeddings import EmbeddingError, embed
    from ..services.extract import ExtractError, chunk_text, extract

    _write(actor)
    row = db.execute(select(Document).where(Document.tenant_id == actor.tenant_id, Document.id == doc_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    # Bytes come from the storage driver, not from treating `storage_key` as a
    # filesystem path, so extraction works identically on a volume or a bucket.
    try:
        payload = get_storage().read(row.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={
            "code": "DOC_STORAGE_UNAVAILABLE",
            "message": "Document bytes could not be read",
            "details": {"error": type(exc).__name__}}) from exc
    if sha256_hex(payload) != row.sha256:
        row.status = "quarantined"
        record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="DOCUMENT_QUARANTINED",
                     resource="document", resource_id=row.id,
                     after={"reason": "integrity-check-failed"}, source="system", created_by=actor.sub)
        db.commit()
        raise HTTPException(status_code=409, detail="Stored bytes failed integrity check")
    try:
        result = extract(row.filename, payload)
    except ExtractError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message,
                                                      "details": exc.details}) from exc
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
