"""Sourcing API — RFQ → Quote → Award, premium comparison ready.

- RFQs: premium-grid list (search/status/currency), create with lines, lifecycle PATCH.
- Quotes: one per supplier per RFQ, lines with integer money, server-computed totals.
- Comparison: GET /rfqs/{id}/comparison — real per-supplier totals from lines
  (the data premium comparison tables render; no synthetic bands).
- Award: POST /rfqs/{id}/award {quote_id, reason} — server total, single winner,
  RFQ → awarded. Audit: RFQ_CREATED/SENT, QUOTE_RECEIVED/SUBMITTED, AWARD_DECIDED.
"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.sourcing import Award, Quote, QuoteLine, Rfq, RfqLine
from ..models.spend import SavingsRecord
from ..models.supplier import Category, Supplier
from ..services.audit import record_event
from ..services.refs import require_ref
from ..services.sourcing import SourcingError, check_quote_transition, check_rfq_transition, line_total

router = APIRouter(tags=["sourcing"])
WRITE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer", "Category Manager"}


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _write(actor: Actor) -> None:
    # Fail-closed: empty/missing roles can never write.
    if not set(actor.roles or ()) & WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for sourcing write")


class RfqLineIn(BaseModel):
    description: str = Field(min_length=2, max_length=500)
    quantity: int = Field(ge=1)
    uom: str = "each"


class RfqIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    title: str = Field(min_length=2, max_length=300)
    currency: str = ""
    category_id: str = ""
    notes: str = ""
    lines: list[RfqLineIn] = Field(default_factory=list)


class RfqStatusIn(BaseModel):
    status: str


class QuoteLineIn(BaseModel):
    rfq_line_id: str = ""
    unit_price_minor: int = Field(gt=0)
    quantity: int = Field(gt=0)


class QuoteIn(BaseModel):
    supplier_id: str = Field(min_length=1)
    currency: str = ""
    lines: list[QuoteLineIn] = Field(min_length=1)


class AwardIn(BaseModel):
    quote_id: str = Field(min_length=1)
    reason: str = ""


def _rfq_dto(r: Rfq, nlines: int = 0) -> dict:
    return {"id": r.id, "code": r.code, "title": r.title, "status": r.status,
            "currency": r.currency, "categoryId": r.category_id, "notes": r.notes,
            "lineCount": nlines, "createdAt": r.created_at.isoformat() if r.created_at else ""}


@router.get("/rfqs")
def list_rfqs(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
              limit: int = Query(default=25, ge=1, le=100), cursor: str = Query(default=""),
              sort: str = Query(default="created_at"), order: str = Query(default="desc"),
              search: str = Query(default=""), status_: str = Query(default="", alias="status")) -> dict:
    if sort not in {"created_at", "code", "title", "status"}:
        raise HTTPException(status_code=422, detail="Invalid sort")
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid order")
    col = {"created_at": Rfq.created_at, "code": Rfq.code, "title": Rfq.title, "status": Rfq.status}[sort]
    stmt = select(Rfq).where(Rfq.tenant_id == actor.tenant_id)
    if status_:
        stmt = stmt.where(Rfq.status == status_)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Rfq.title.ilike(like), Rfq.code.ilike(like)))
    if cursor:
        cur_row = db.execute(select(Rfq).where(Rfq.tenant_id == actor.tenant_id, Rfq.id == cursor)).scalar_one_or_none()
        if cur_row is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        cur_val = getattr(cur_row, sort)
        if order == "desc":
            stmt = stmt.where(or_(col < cur_val, ((col == cur_val) & (Rfq.id < cursor))))
        else:
            stmt = stmt.where(or_(col > cur_val, ((col == cur_val) & (Rfq.id > cursor))))
    stmt = stmt.order_by(asc(col) if order == "asc" else desc(col), asc(Rfq.id) if order == "asc" else desc(Rfq.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more, rows = len(rows) > limit, rows[:limit]
    return envelope([_rfq_dto(r) for r in rows],
                    {"limit": limit, "nextCursor": rows[-1].id if has_more and rows else "", "hasMore": has_more}, getattr(request.state, "request_id", ""))


@router.post("/rfqs", status_code=201)
def create_rfq(payload: RfqIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    code = payload.code.strip().upper()
    if len(code) < 2:
        raise HTTPException(status_code=422, detail="Invalid RFQ code")
    ccy = payload.currency.strip().upper()
    category_id = require_ref(db, Category, actor.tenant_id, payload.category_id, field="category_id", code="UNKNOWN_CATEGORY")
    r = Rfq(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, code=code,
            title=payload.title.strip(), status="draft", currency=ccy,
            category_id=category_id, notes=payload.notes.strip())
    db.add(r)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="RFQ code already exists in this tenant") from exc
    for i, ln in enumerate(payload.lines, start=1):
        db.add(RfqLine(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                       rfq_id=r.id, line_no=i, description=ln.description.strip(), quantity=ln.quantity, uom=ln.uom.strip() or "each"))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="RFQ_CREATED", resource="rfq",
                 resource_id=r.id, after={"code": code, "lines": len(payload.lines)}, source="api",
                 ip=request.client.host if request.client else "", created_by=actor.sub)
    db.commit()
    db.refresh(r)
    return envelope(_rfq_dto(r, len(payload.lines)), None, getattr(request.state, "request_id", ""))


@router.get("/rfqs/{rfq_id}")
def get_rfq(rfq_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    r = db.execute(select(Rfq).where(Rfq.tenant_id == actor.tenant_id, Rfq.id == rfq_id)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    lines = list(db.execute(select(RfqLine).where(RfqLine.tenant_id == actor.tenant_id, RfqLine.rfq_id == rfq_id).order_by(RfqLine.line_no)).scalars())
    quotes = list(db.execute(select(Quote).where(Quote.tenant_id == actor.tenant_id, Quote.rfq_id == rfq_id)).scalars())
    dto = _rfq_dto(r, len(lines))
    dto["lines"] = [{"id": l.id, "lineNo": l.line_no, "description": l.description, "quantity": l.quantity, "uom": l.uom} for l in lines]
    dto["quotes"] = [{"id": q.id, "supplierId": q.supplier_id, "status": q.status, "totalMinor": q.total_minor} for q in quotes]
    return envelope(dto, None, getattr(request.state, "request_id", ""))


@router.patch("/rfqs/{rfq_id}/status")
def move_rfq(rfq_id: str, payload: RfqStatusIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    r = db.execute(select(Rfq).where(Rfq.tenant_id == actor.tenant_id, Rfq.id == rfq_id)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    try:
        check_rfq_transition(r.status, payload.status)
    except SourcingError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    before = r.status
    r.status, r.updated_by = payload.status, actor.sub
    if payload.status == "evaluated":
        # Evaluation phase evaluates every submitted quote server-side.
        for q in db.execute(select(Quote).where(Quote.tenant_id == actor.tenant_id, Quote.rfq_id == rfq_id, Quote.status == "submitted")).scalars():
            q.status = "evaluated"
            q.updated_by = actor.sub
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="RFQ_SENT" if payload.status == "sent" else "RFQ_STATUS_CHANGED",
                 resource="rfq", resource_id=r.id, before={"status": before}, after={"status": r.status}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(r)
    return envelope(_rfq_dto(r), None, getattr(request.state, "request_id", ""))


@router.post("/rfqs/{rfq_id}/quotes", status_code=201)
def submit_quote(rfq_id: str, payload: QuoteIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    r = db.execute(select(Rfq).where(Rfq.tenant_id == actor.tenant_id, Rfq.id == rfq_id)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if r.status not in {"sent", "response"}:
        raise HTTPException(status_code=422, detail="RFQ is not accepting quotes in its current status")
    sup = db.execute(select(Supplier).where(Supplier.tenant_id == actor.tenant_id, Supplier.id == payload.supplier_id)).scalar_one_or_none()
    if sup is None:
        raise HTTPException(status_code=422, detail="Unknown supplier for this tenant")
    # A quote line must point at a line of *this* RFQ. Unvalidated, a quote could
    # cite an arbitrary (or another tenant's) rfq_line id, and since award totals
    # and savings are derived from these lines, that poisons the money chain.
    rfq_line_ids = [ln.id for ln in db.execute(select(RfqLine).where(
        RfqLine.tenant_id == actor.tenant_id, RfqLine.rfq_id == rfq_id)).scalars()]
    for ln in payload.lines:
        if (ln.rfq_line_id or "").strip() and ln.rfq_line_id.strip() not in rfq_line_ids:
            raise HTTPException(status_code=422, detail={
                "code": "QUOTE_LINE_NOT_ON_RFQ",
                "message": "lines[].rfq_line_id must reference a line of this RFQ",
                "details": {"rfqLineId": ln.rfq_line_id, "rfqId": rfq_id},
            })
    q = Quote(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, rfq_id=rfq_id,
              supplier_id=payload.supplier_id, status="submitted", currency=(payload.currency or r.currency).strip().upper())
    db.add(q)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A quote from this supplier already exists for this RFQ") from exc
    total = 0
    try:
        for ln in payload.lines:
            lt = line_total(ln.unit_price_minor, ln.quantity)
            total += lt
            db.add(QuoteLine(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                             quote_id=q.id, rfq_line_id=ln.rfq_line_id, unit_price_minor=ln.unit_price_minor,
                             quantity=ln.quantity, line_total_minor=lt))
    except SourcingError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    q.total_minor = total
    if r.status == "sent":
        r.status = "response"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="QUOTE_RECEIVED", resource="quote",
                 resource_id=q.id, after={"rfq": rfq_id, "supplier": payload.supplier_id, "total_minor": total}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(q)
    return envelope({"id": q.id, "status": q.status, "totalMinor": q.total_minor}, None, getattr(request.state, "request_id", ""))


@router.get("/rfqs/{rfq_id}/comparison")
def comparison(rfq_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    r = db.execute(select(Rfq).where(Rfq.tenant_id == actor.tenant_id, Rfq.id == rfq_id)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    quotes = list(db.execute(select(Quote).where(Quote.tenant_id == actor.tenant_id, Quote.rfq_id == rfq_id).order_by(Quote.total_minor)).scalars())
    # Two grouped queries instead of two per quote. This endpoint backs the
    # award decision, so its latency is on the critical path of a real spend.
    names: dict[str, str] = {}
    if quotes:
        names = {r[0]: r[1] for r in db.execute(
            select(Supplier.id, Supplier.name).where(Supplier.tenant_id == actor.tenant_id,
                                                      Supplier.id.in_([q.supplier_id for q in quotes]))).all()}
    line_counts: dict[str, int] = {}
    if quotes:
        line_counts = {r[0]: int(r[1]) for r in db.execute(
            select(QuoteLine.quote_id, func.count()).where(QuoteLine.tenant_id == actor.tenant_id,
                                                           QuoteLine.quote_id.in_([q.id for q in quotes]))
            .group_by(QuoteLine.quote_id)).all()}
    rows = [{"quoteId": q.id, "supplierId": q.supplier_id, "supplierName": names.get(q.supplier_id, "?"),
             "status": q.status, "currency": q.currency, "totalMinor": q.total_minor,
             "lineCount": int(line_counts.get(q.id, 0))} for q in quotes]
    return envelope(rows, {"count": len(rows), "currency": r.currency}, getattr(request.state, "request_id", ""))


@router.post("/rfqs/{rfq_id}/award", status_code=201)
def award(rfq_id: str, payload: AwardIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    r = db.execute(select(Rfq).where(Rfq.tenant_id == actor.tenant_id, Rfq.id == rfq_id)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    exists = db.execute(select(Award).where(Award.tenant_id == actor.tenant_id, Award.rfq_id == rfq_id)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="RFQ already awarded")
    if r.status != "evaluated":
        raise HTTPException(status_code=422, detail="RFQ must be evaluated before award")
    q = db.execute(select(Quote).where(Quote.tenant_id == actor.tenant_id, Quote.id == payload.quote_id, Quote.rfq_id == rfq_id)).scalar_one_or_none()
    if q is None:
        raise HTTPException(status_code=422, detail="Quote does not belong to this RFQ")
    if q.status == "rejected":
        raise HTTPException(status_code=422, detail="Rejected quotes cannot be awarded")
    # Server-computed total from lines (never trust client).
    lines = list(db.execute(select(QuoteLine).where(QuoteLine.tenant_id == actor.tenant_id, QuoteLine.quote_id == q.id)).scalars())
    server_total = sum(l.line_total_minor for l in lines)
    # Savings baseline, captured BEFORE any status is flipped below, in one
    # grouped query. It used to be computed after rejecting the losers and by
    # re-selecting each quote's lines, so the comparison set was always just the
    # winner — every award recorded zero savings — and it cost one query per
    # competing quote on top of that.
    competing = {o.id for o in db.execute(select(Quote).where(
        Quote.tenant_id == actor.tenant_id, Quote.rfq_id == rfq_id,
        Quote.status.in_(["submitted", "evaluated"]))).scalars()}
    line_totals: dict[str, int] = {}
    if competing:
        line_totals = {r[0]: int(r[1] or 0) for r in db.execute(
            select(QuoteLine.quote_id, func.coalesce(func.sum(QuoteLine.line_total_minor), 0))
            .where(QuoteLine.tenant_id == actor.tenant_id, QuoteLine.quote_id.in_(competing))
            .group_by(QuoteLine.quote_id)).all()}
    try:
        check_quote_transition(q.status, "awarded")
    except SourcingError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    a = Award(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, rfq_id=rfq_id,
              quote_id=q.id, reason=payload.reason.strip(), awarded_total_minor=server_total)
    db.add(a)
    db.flush()
    q.status = "awarded"
    r.status = "awarded"
    # Reject all other submitted/evaluated quotes on this RFQ.
    for qid in competing:
        if qid == q.id:
            continue
        other = db.get(Quote, qid)
        if other is not None and other.status in {"submitted", "evaluated"}:
            other.status = "rejected"
    # Savings = highest competing total − awarded total, all recomputed from lines.
    peak = max([server_total, *line_totals.values()]) if line_totals else server_total
    if peak > server_total:
        db.add(SavingsRecord(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                             rfq_id=rfq_id, award_id=a.id, currency=r.currency, saved_minor=peak - server_total))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="AWARD_DECIDED", resource="award",
                 resource_id=a.id, after={"rfq": rfq_id, "quote": q.id, "total_minor": server_total, "reason": payload.reason}, source="api", created_by=actor.sub)
    from ..services.notify import notify as _notify

    _notify(db, tenant_id=actor.tenant_id, kind="AWARD_DECIDED", title=f"RFQ {r.code} awarded",
            body=f"Winner total {server_total}.", link="/rfqs", created_by=actor.sub)
    db.commit()
    db.refresh(a)
    return envelope({"id": a.id, "quoteId": q.id, "awardedTotalMinor": server_total}, None, getattr(request.state, "request_id", ""))


class OptimizeIn(BaseModel):
    max_share_bp: int = Field(default=10_000, ge=1, le=10_000)
    exclude: list[str] = Field(default_factory=list)


@router.post("/rfqs/{rfq_id}/optimize")
def optimize(rfq_id: str, payload: OptimizeIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """06 optimizer: cheapest feasible split across evaluated quotes (read-only)."""
    from ..services.optimizer import OptimizerError, allocate

    r = db.execute(select(Rfq).where(Rfq.tenant_id == actor.tenant_id, Rfq.id == rfq_id)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    quotes = [{"supplier_id": q.supplier_id, "quote_id": q.id, "total_minor": q.total_minor}
              for q in db.execute(select(Quote).where(Quote.tenant_id == actor.tenant_id, Quote.rfq_id == rfq_id,
                                                      Quote.status.in_(["submitted", "evaluated", "awarded"]))).scalars()]
    try:
        out = allocate(quotes=quotes, max_share_bp=payload.max_share_bp, exclude=set(payload.exclude))
    except OptimizerError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="RFQ_OPTIMIZED", resource="rfq",
                 resource_id=rfq_id, after={"total_minor": out["total_minor"], "legs": len(out["allocations"])}, source="api", created_by=actor.sub)
    db.commit()
    return envelope(out, None, getattr(request.state, "request_id", ""))
