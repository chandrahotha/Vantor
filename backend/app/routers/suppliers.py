"""Supplier API — premium-grid ready, real data only.

- GET /api/v1/suppliers: cursor pagination (limit/cursor/sort/order/search/status),
  stable newest-first default, typed 422 on bad sort.
- POST /api/v1/suppliers: validated create + SUPPLIER_CREATED audit + duplicate hint.
- GET/PATCH /api/v1/suppliers/{id}: tenant-scoped, SUPPLIER_UPDATED audit.
- Contacts: GET/POST /api/v1/suppliers/{id}/contacts (real rows, no synthetics).

Grid contract (all future modules reuse): {data[], pagination{limit,nextCursor,hasMore,sort,order}}.
Dashboards/reporting aggregate from these rows — never from fixtures.
"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.document import Document
from ..models.scorecard import SupplierScorecard
from ..models.onboarding import SupplierCertification, SupplierQualification
from ..models.supplier import Category, Supplier, SupplierContact
from ..services.audit import record_event
from ..services.names import category_names
from ..services.refs import require_ref
from ..services.scoring import DEFAULT_WEIGHTS, ScoringError, score as score_supplier
from ..services.supplier import (
    SupplierError,
    check_lifecycle,
    find_possible_duplicate,
    normalize_code,
    validate_payload,
)

router = APIRouter(tags=["suppliers"])

WRITE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer", "Category Manager", "Supplier Manager"}

#: VNT-025/026. Verifying a certification and deciding a qualification are
#: *judgements about a third party's evidence*, and they were both guarded by the
#: same set that lets you edit your own supplier record. That is not a separation
#: of duties, it is a naming convention: a `Buyer` verified the certificates of
#: the supplier they were onboarding, and a `Supplier Manager` qualified their own
#: employer.
#:
#: Both are now capabilities with their own role sets, and both additionally
#: refuse the submitter. `Compliance Reviewer` is the role a deployment assigns to
#: whoever owns supplier risk; a tenant that has not created it yet must map the
#: duty onto Procurement Manager, which is explicit rather than accidental.
VERIFY_CERT_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin",
                     "Procurement Manager", "Compliance Reviewer"}
DECIDE_QUAL_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin",
                     "Compliance Reviewer"}


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _require_write(actor: Actor) -> None:
    # Fail-closed: empty/missing roles can never write.
    if not set(actor.roles or ()) & WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for supplier write")


def _require(actor: Actor, action: str) -> None:
    """Authority for one named judgement. The single gate both use."""
    allowed = {"verify_cert": VERIFY_CERT_ROLES, "decide_qual": DECIDE_QUAL_ROLES}[action]
    if not set(actor.roles or ()) & allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "code": "SUPPLIER_ACTION_FORBIDDEN",
            "message": f"Role required for this supplier action: {action}",
            "details": {"action": action, "allowedRoles": sorted(allowed)},
        })


class SupplierIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=300)
    status: str = "draft"
    country: str = ""
    currency: str = ""
    category_id: str = ""
    payment_terms: str = ""
    notes: str = ""


class SupplierPatch(BaseModel):
    name: str | None = None
    status: str | None = None
    country: str | None = None
    currency: str | None = None
    category_id: str | None = None
    payment_terms: str | None = None
    notes: str | None = None


class ContactIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: str = ""
    phone: str = ""
    role: str = ""


def _to_dto(s: Supplier, duplicate_of: str = "", category_name: str = "") -> dict:
    return {
        "id": s.id,
        "code": s.code,
        "name": s.name,
        "status": s.status,
        "country": s.country,
        "currency": s.currency,
        "categoryId": s.category_id,
        "categoryName": category_name,
        "paymentTerms": s.payment_terms,
        "riskTier": s.risk_tier,
        "notes": s.notes,
        "createdAt": s.created_at.isoformat() if s.created_at else "",
        "updatedAt": s.updated_at.isoformat() if s.updated_at else "",
        "possibleDuplicateOf": duplicate_of,
    }


@router.get("/suppliers")
def list_suppliers(
    request: Request,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(db_for_actor),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str = Query(default=""),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc"),
    search: str = Query(default=""),
    status_: str = Query(default="", alias="status"),
) -> dict:
    if sort not in {"created_at", "name", "code", "status"}:
        raise HTTPException(status_code=422, detail="Invalid sort (created_at|name|code|status)")
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid order (asc|desc)")
    col = {"created_at": Supplier.created_at, "name": Supplier.name, "code": Supplier.code, "status": Supplier.status}[sort]
    stmt = select(Supplier).where(Supplier.tenant_id == actor.tenant_id)
    if status_:
        stmt = stmt.where(Supplier.status == status_)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Supplier.name.ilike(like), Supplier.code.ilike(like)))
    if cursor:
        # Keyset on (sort_col, id): fetch cursor row, then page strictly after it.
        cur_row = db.execute(select(Supplier).where(Supplier.tenant_id == actor.tenant_id, Supplier.id == cursor)).scalar_one_or_none()
        if cur_row is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        cur_val = getattr(cur_row, sort)
        if order == "desc":
            stmt = stmt.where(or_(col < cur_val, ((col == cur_val) & (Supplier.id < cursor))))
        else:
            stmt = stmt.where(or_(col > cur_val, ((col == cur_val) & (Supplier.id > cursor))))
    stmt = stmt.order_by(asc(col) if order == "asc" else desc(col), asc(Supplier.id) if order == "asc" else desc(Supplier.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = rows[-1].id if has_more and rows else ""
    rid = getattr(request.state, "request_id", "")
    cat_names = category_names(db, actor.tenant_id, {r.category_id for r in rows})
    return envelope([_to_dto(r, category_name=cat_names.get(r.category_id or "", "")) for r in rows],
                    {"limit": limit, "nextCursor": next_cursor, "hasMore": has_more, "sort": sort, "order": order}, rid)


@router.post("/suppliers", status_code=201)
def create_supplier(payload: SupplierIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _require_write(actor)
    try:
        code = normalize_code(payload.code)
        name, st, ccy, ctry = validate_payload(payload.name, payload.status, payload.currency, payload.country)
    except SupplierError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    dup = find_possible_duplicate(db, tenant_id=actor.tenant_id, name=name, country=ctry)
    category_id = require_ref(db, Category, actor.tenant_id, payload.category_id, field="category_id", code="UNKNOWN_CATEGORY")
    row = Supplier(
        tenant_id=actor.tenant_id,
        created_by=actor.sub,
        updated_by=actor.sub,
        code=code,
        name=name,
        status=st,
        country=ctry,
        currency=ccy,
        category_id=category_id,
        payment_terms=(payload.payment_terms or "").strip(),
        notes=(payload.notes or "").strip(),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Supplier code already exists in this tenant") from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="SUPPLIER_CREATED", resource="supplier",
                 resource_id=row.id, after={"code": code, "name": name}, source="api",
                 ip=request.client.host if request.client else "", created_by=actor.sub)
    db.commit()
    db.refresh(row)
    rid = getattr(request.state, "request_id", "")
    cat_names = category_names(db, actor.tenant_id, {row.category_id})
    return envelope(_to_dto(row, dup, category_name=cat_names.get(row.category_id or "", "")), None, rid)


@router.get("/suppliers/{supplier_id}")
def get_supplier(supplier_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    row = db.execute(select(Supplier).where(Supplier.tenant_id == actor.tenant_id, Supplier.id == supplier_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    cat_names = category_names(db, actor.tenant_id, {row.category_id})
    return envelope(_to_dto(row, category_name=cat_names.get(row.category_id or "", "")), None, getattr(request.state, "request_id", ""))


@router.patch("/suppliers/{supplier_id}")
def update_supplier(supplier_id: str, payload: SupplierPatch, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _require_write(actor)
    row = db.execute(select(Supplier).where(Supplier.tenant_id == actor.tenant_id, Supplier.id == supplier_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    before = {"name": row.name, "status": row.status}
    try:
        if payload.name is not None or payload.status is not None or payload.currency is not None or payload.country is not None:
            name, st, ccy, ctry = validate_payload(
                payload.name if payload.name is not None else row.name,
                payload.status if payload.status is not None else row.status,
                payload.currency if payload.currency is not None else row.currency,
                payload.country if payload.country is not None else row.country,
            )
            check_lifecycle(row.status, st)
            row.name, row.status, row.currency, row.country = name, st, ccy, ctry
        for f in ("category_id", "payment_terms", "notes"):
            v = getattr(payload, f)
            if v is None:
                continue
            # Re-parenting a supplier must not leave it pointing at a category
            # that does not exist (or one from another tenant).
            setattr(row, f, require_ref(db, Category, actor.tenant_id, v, field=f, code="UNKNOWN_CATEGORY")
                    if f == "category_id" else v.strip())
        row.updated_by = actor.sub
        db.flush()
    except SupplierError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="SUPPLIER_UPDATED", resource="supplier",
                 resource_id=row.id, before=before, after={"name": row.name, "status": row.status},
                 source="api", ip=request.client.host if request.client else "", created_by=actor.sub)
    db.commit()
    db.refresh(row)
    cat_names = category_names(db, actor.tenant_id, {row.category_id})
    return envelope(_to_dto(row, category_name=cat_names.get(row.category_id or "", "")), None, getattr(request.state, "request_id", ""))


@router.get("/suppliers/{supplier_id}/contacts")
def list_contacts(supplier_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    sup = db.execute(select(Supplier).where(Supplier.tenant_id == actor.tenant_id, Supplier.id == supplier_id)).scalar_one_or_none()
    if sup is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    rows = list(db.execute(select(SupplierContact).where(SupplierContact.tenant_id == actor.tenant_id, SupplierContact.supplier_id == supplier_id).order_by(SupplierContact.created_at)).scalars())
    data = [{"id": c.id, "fullName": c.full_name, "email": c.email, "phone": c.phone, "role": c.role} for c in rows]
    return envelope(data, {"limit": len(data), "nextCursor": "", "hasMore": False, "count": len(data)}, getattr(request.state, "request_id", ""))


@router.post("/suppliers/{supplier_id}/contacts", status_code=201)
def add_contact(supplier_id: str, payload: ContactIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _require_write(actor)
    sup = db.execute(select(Supplier).where(Supplier.tenant_id == actor.tenant_id, Supplier.id == supplier_id)).scalar_one_or_none()
    if sup is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    c = SupplierContact(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                        supplier_id=supplier_id, full_name=payload.full_name.strip(),
                        email=payload.email.strip(), phone=payload.phone.strip(), role=payload.role.strip())
    db.add(c)
    db.flush()
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="SUPPLIER_CONTACT_ADDED", resource="supplier",
                 resource_id=supplier_id, after={"contact": c.full_name}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(c)
    return envelope({"id": c.id, "fullName": c.full_name}, None, getattr(request.state, "request_id", ""))


class ScorecardIn(BaseModel):
    dims: dict[str, int]
    weights: dict[str, int] | None = None
    hard_flags: int = Field(default=0, ge=0)


@router.post("/suppliers/{supplier_id}/scorecard", status_code=201)
def post_scorecard(supplier_id: str, payload: ScorecardIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _require_write(actor)
    sup = db.execute(select(Supplier).where(Supplier.tenant_id == actor.tenant_id, Supplier.id == supplier_id)).scalar_one_or_none()
    if sup is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    try:
        result = score_supplier(dims=payload.dims, weights=payload.weights or dict(DEFAULT_WEIGHTS), hard_flags=payload.hard_flags)
    except ScoringError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    row = SupplierScorecard(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, supplier_id=supplier_id,
                            score=result["score"], grade=result["grade"], risk_tier=result["risk_tier"],
                            dims=result["dims"], weights=payload.weights or dict(DEFAULT_WEIGHTS), hard_flags=payload.hard_flags)
    db.add(row)
    db.flush()
    sup.risk_tier = result["risk_tier"]
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="SUPPLIER_SCORED", resource="supplier",
                 resource_id=supplier_id, after={"score": result["score"], "grade": result["grade"]}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(row)
    return envelope({"id": row.id, **result}, None, getattr(request.state, "request_id", ""))


@router.get("/suppliers/{supplier_id}/scorecard")
def get_scorecard(supplier_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    sup = db.execute(select(Supplier).where(Supplier.tenant_id == actor.tenant_id, Supplier.id == supplier_id)).scalar_one_or_none()
    if sup is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    row = db.execute(select(SupplierScorecard).where(
        SupplierScorecard.tenant_id == actor.tenant_id, SupplierScorecard.supplier_id == supplier_id
    ).order_by(SupplierScorecard.created_at.desc(), SupplierScorecard.id.desc()).limit(1)).scalar_one_or_none()
    if row is None:
        return envelope(None, None, getattr(request.state, "request_id", ""))
    return envelope({"id": row.id, "score": row.score, "grade": row.grade, "risk_tier": row.risk_tier,
                     "dims": row.dims, "createdAt": row.created_at.isoformat() if row.created_at else ""}, None, getattr(request.state, "request_id", ""))


class CertIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    issuer: str = ""
    valid_until: str = ""
    document_id: str = ""


class DecideIn(BaseModel):
    decision: str  # qualified | rejected
    reason: str = ""


def _supplier_or_404(db: Session, tenant_id: str, supplier_id: str) -> Supplier:
    sup = db.execute(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.id == supplier_id)).scalar_one_or_none()
    if sup is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return sup


@router.get("/suppliers/{supplier_id}/certifications")
def list_certs(supplier_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _supplier_or_404(db, actor.tenant_id, supplier_id)
    rows = list(db.execute(select(SupplierCertification).where(
        SupplierCertification.tenant_id == actor.tenant_id, SupplierCertification.supplier_id == supplier_id)
        .order_by(SupplierCertification.created_at)).scalars())
    return envelope([{"id": r.id, "name": r.name, "issuer": r.issuer, "validUntil": r.valid_until, "status": r.status} for r in rows],
                    {"count": len(rows)}, getattr(request.state, "request_id", ""))


@router.post("/suppliers/{supplier_id}/certifications", status_code=201)
def add_cert(supplier_id: str, payload: CertIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _require_write(actor)
    _supplier_or_404(db, actor.tenant_id, supplier_id)
    if payload.valid_until:
        from ..services.contract import parse_iso_day

        try:
            parse_iso_day(payload.valid_until, "valid_until")
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    # A certification is evidence. Accepting a document_id that does not exist
    # (or belongs to another tenant) lets a supplier be "qualified" against
    # evidence nobody can ever open, which is the whole point of the gate.
    document_id = require_ref(db, Document, actor.tenant_id, payload.document_id,
                             field="document_id", code="UNKNOWN_DOCUMENT")
    row = SupplierCertification(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, supplier_id=supplier_id,
                                name=payload.name.strip(), issuer=payload.issuer.strip(), valid_until=payload.valid_until.strip(),
                                status="pending", document_id=document_id)
    db.add(row)
    db.flush()
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CERT_SUBMITTED", resource="supplier",
                 resource_id=supplier_id, after={"cert": row.name}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(row)
    return envelope({"id": row.id}, None, getattr(request.state, "request_id", ""))


@router.post("/suppliers/{supplier_id}/certifications/{cert_id}/verify", status_code=200)
def verify_cert(supplier_id: str, cert_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Verify a certification.

    VNT-025. Three things were missing and each of them is a control:

    * **Authority.** The role was a generic write role, so a `Buyer` verified
      the certificates of their own supplier. Verification is now a distinct
      capability.
    * **Segregation of duties.** There was none: the project's own test had the
      submitting identity call `/verify` and get 200. The submitter is refused.
    * **Evidence.** The document behind the certification was never opened. It is
      now loaded, and it must be readable in this tenant and not quarantined —
      otherwise "verified" meant "the row said so", which is the definition of a
      rubber stamp.
    * **Currency.** A certification whose `valid_until` has passed cannot be
      verified. Verifying an expired document is worse than refusing to verify a
      current one.
    """
    _require(actor, "verify_cert")
    row = db.execute(select(SupplierCertification).where(
        SupplierCertification.tenant_id == actor.tenant_id, SupplierCertification.id == cert_id,
        SupplierCertification.supplier_id == supplier_id).with_for_update()).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Certification not found")
    if row.status not in {"pending", "rejected"}:
        raise HTTPException(status_code=409, detail={
            "code": "CERT_ALREADY_DECIDED",
            "message": f"This certification is already {row.status}"})
    if row.created_by and row.created_by == actor.sub:
        raise HTTPException(status_code=403, detail={
            "code": "CERT_SOD",
            "message": "The submitter of a certification cannot verify it (segregation of duties)"})
    today = _today()
    if row.valid_until and row.valid_until < today.isoformat():
        raise HTTPException(status_code=422, detail={
            "code": "CERT_EXPIRED",
            "message": f"This certification expired on {row.valid_until}",
            "details": {"validUntil": row.valid_until, "today": today.isoformat()}})
    if row.document_id:
        from ..models.document import Document

        evidence = db.execute(select(Document).where(
            Document.tenant_id == actor.tenant_id, Document.id == row.document_id)).scalar_one_or_none()
        if evidence is None:
            raise HTTPException(status_code=422, detail={
                "code": "CERT_EVIDENCE_MISSING",
                "message": "The evidence document for this certification does not exist in this tenant",
                "details": {"documentId": row.document_id}})
        if evidence.status == "quarantined":
            raise HTTPException(status_code=422, detail={
                "code": "CERT_EVIDENCE_QUARANTINED",
                "message": "The evidence document is quarantined and cannot support a verification",
                "details": {"documentId": evidence.id, "status": evidence.status}})
    row.status, row.updated_by = "verified", actor.sub
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CERT_VERIFIED", resource="supplier",
                 resource_id=supplier_id,
                 after={"cert": row.name, "issuer": row.issuer, "validUntil": row.valid_until,
                        "documentId": row.document_id or "", "asOf": today.isoformat()},
                 source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": row.id, "status": "verified"}, None, getattr(request.state, "request_id", ""))


def _today():
    from datetime import date as _date

    return _date.today()


class CertDecisionIn(BaseModel):
    reject: bool = False
    reason: str = Field(default="", max_length=1000)


@router.get("/suppliers/{supplier_id}/qualification")
def get_qual(supplier_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _supplier_or_404(db, actor.tenant_id, supplier_id)
    row = db.execute(select(SupplierQualification).where(
        SupplierQualification.tenant_id == actor.tenant_id, SupplierQualification.supplier_id == supplier_id)).scalar_one_or_none()
    if row is None:
        return envelope({"status": "draft", "exists": False}, None, getattr(request.state, "request_id", ""))
    return envelope({"status": row.status, "exists": True, "checklist": row.checklist}, None, getattr(request.state, "request_id", ""))


@router.post("/suppliers/{supplier_id}/qualification/submit", status_code=200)
def submit_qual(supplier_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _require_write(actor)
    _supplier_or_404(db, actor.tenant_id, supplier_id)
    row = db.execute(select(SupplierQualification).where(
        SupplierQualification.tenant_id == actor.tenant_id, SupplierQualification.supplier_id == supplier_id)).scalar_one_or_none()
    if row is None:
        row = SupplierQualification(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                                    supplier_id=supplier_id, status="draft", checklist={})
        db.add(row)
        db.flush()
    if row.status not in {"draft", "rejected", "submitted"}:
        raise HTTPException(status_code=422, detail="Qualification already under review or qualified")
    certs = list(db.execute(select(SupplierCertification).where(
        SupplierCertification.tenant_id == actor.tenant_id, SupplierCertification.supplier_id == supplier_id)).scalars())
    verified = sum(1 for c in certs if c.status == "verified")
    latest = db.execute(select(SupplierScorecard).where(
        SupplierScorecard.tenant_id == actor.tenant_id, SupplierScorecard.supplier_id == supplier_id)
        .order_by(SupplierScorecard.created_at.desc()).limit(1)).scalar_one_or_none()
    checklist = {"certifications_total": len(certs), "certifications_verified": verified,
                 "scorecard_grade": latest.grade if latest else None}
    row.checklist, row.status, row.updated_by = checklist, "submitted", actor.sub
    # Auto-advance: evidence complete (>=1 verified cert + grade C or better) => under_review.
    if verified >= 1 and latest is not None and latest.grade in {"A", "B", "C"}:
        row.status = "under_review"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="QUALIFICATION_SUBMITTED", resource="supplier",
                 resource_id=supplier_id, after={"status": row.status, **checklist}, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"status": row.status, "checklist": checklist}, None, getattr(request.state, "request_id", ""))


@router.post("/suppliers/{supplier_id}/qualification/decide", status_code=200)
def decide_qual(supplier_id: str, payload: DecideIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Decide a supplier qualification.

    VNT-026. The decision used to be guarded by the flat supplier write set, so
    `Buyer`, `Category Manager` and `Supplier Manager` could all qualify a
    supplier — including the supplier's own manager. Authority is now a distinct
    `decide_qual` capability.

    Two further controls the audit named, both added because a qualified supplier
    can bid on a contract:

    * A rejection needs a written reason. `reason` defaulted to `""` and nothing
      rejected the empty case, so a supplier could be refused with no explanation
      recorded anywhere.
    * The evidence is re-checked at decision time, not only at submission. The
      submission-time check is in `submit_qual`; repeating it here is what stops a
      certification being withdrawn between submission and decision.
    """
    _require(actor, "decide_qual")
    if payload.decision not in {"qualified", "rejected"}:
        raise HTTPException(status_code=422, detail="decision must be qualified|rejected")
    if payload.decision == "rejected" and not payload.reason.strip():
        raise HTTPException(status_code=422, detail={
            "code": "REASON_REQUIRED",
            "message": "A rejection needs a written reason",
            "details": {"field": "reason"}})
    row = db.execute(select(SupplierQualification).where(
        SupplierQualification.tenant_id == actor.tenant_id,
        SupplierQualification.supplier_id == supplier_id).with_for_update()).scalar_one_or_none()
    if row is None or row.status != "under_review":
        raise HTTPException(status_code=422, detail="Qualification must be under review to decide")
    if row.created_by == actor.sub:
        raise HTTPException(status_code=403, detail="Submitter cannot decide their own case (segregation of duties)")
    if payload.decision == "qualified":
        # Re-verify the evidence at decision time. `submit_qual` checked it
        # earlier; a certification can be quarantined or expire in between, and a
        # qualified supplier is one that can bid.
        from ..models.document import Document

        certs = list(db.execute(select(SupplierCertification).where(
            SupplierCertification.tenant_id == actor.tenant_id,
            SupplierCertification.supplier_id == supplier_id,
            SupplierCertification.status == "verified")).scalars())
        today = _today().isoformat()
        current = [c for c in certs if not c.valid_until or c.valid_until >= today]
        if not current:
            raise HTTPException(status_code=422, detail={
                "code": "NO_CURRENT_EVIDENCE",
                "message": "No unexpired verified certification supports this qualification",
                "details": {"verified": len(certs), "current": len(current), "today": today}})
        quarantined = []
        for cert in current:
            if not cert.document_id:
                continue
            evidence = db.execute(select(Document).where(
                Document.tenant_id == actor.tenant_id, Document.id == cert.document_id)).scalar_one_or_none()
            if evidence is None or evidence.status == "quarantined":
                quarantined.append(cert.id)
        if quarantined:
            raise HTTPException(status_code=422, detail={
                "code": "EVIDENCE_QUARANTINED",
                "message": "The evidence behind this qualification is missing or quarantined",
                "details": {"certificationIds": quarantined}})
        # The decision snapshot is frozen here, so a later edit to the underlying
        # evidence cannot change what was decided.
        row.checklist = {**(row.checklist or {}),
                         "decidedAt": today,
                         "verifiedCertifications": [c.id for c in current],
                         "evidenceFrozen": True}
    row.status, row.decided_by, row.reason, row.updated_by = payload.decision, actor.sub, payload.reason.strip(), actor.sub
    if payload.decision == "qualified":
        sup = _supplier_or_404(db, actor.tenant_id, supplier_id)
        if sup.status == "draft":
            sup.status = "active"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="QUALIFICATION_DECIDED", resource="supplier",
                 resource_id=supplier_id,
                 after={"decision": payload.decision, "reason": payload.reason.strip(),
                        "checklist": row.checklist}, source="api", created_by=actor.sub)
    from ..services.notify import notify as _notify

    _notify(db, tenant_id=actor.tenant_id, kind="QUALIFICATION_DECIDED",
            title=f"Supplier qualification {payload.decision}", link="/suppliers",
            user_sub=row.created_by, created_by=actor.sub)
    db.commit()
    return envelope({"status": row.status}, None, getattr(request.state, "request_id", ""))
