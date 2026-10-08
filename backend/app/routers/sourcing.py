"""Sourcing API - RFQ → Quote → Award, comparison ready.

- RFQs: data-grid list (search/status/currency), create with lines, lifecycle PATCH.
- Quotes: one per supplier per RFQ, lines with integer money, server-computed totals.
- Comparison: GET /rfqs/{id}/comparison - real per-supplier totals from lines
  (the data comparison tables render; no synthetic bands).
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
from ..models.onboarding import SupplierQualification
from ..services.audit import record_event
from ..services.names import supplier_names
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
    names = supplier_names(db, actor.tenant_id, {q.supplier_id for q in quotes})
    dto = _rfq_dto(r, len(lines))
    dto["lines"] = [{"id": l.id, "lineNo": l.line_no, "description": l.description, "quantity": l.quantity, "uom": l.uom} for l in lines]
    dto["quotes"] = [{"id": q.id, "supplierId": q.supplier_id, "supplierName": names.get(q.supplier_id, ""),
                      "status": q.status, "totalMinor": q.total_minor} for q in quotes]
    award = db.execute(select(Award).where(Award.tenant_id == actor.tenant_id, Award.rfq_id == rfq_id)).scalar_one_or_none()
    if award is not None:
        winner = db.get(Quote, award.quote_id)
        dto["award"] = {"id": award.id, "quoteId": award.quote_id,
                        "supplierId": winner.supplier_id if winner else "",
                        "supplierName": names.get(winner.supplier_id, "") if winner else "",
                        "awardedTotalMinor": award.awarded_total_minor, "reason": award.reason}
    return envelope(dto, None, getattr(request.state, "request_id", ""))


@router.patch("/rfqs/{rfq_id}/status")
def move_rfq(rfq_id: str, payload: RfqStatusIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    r = db.execute(select(Rfq).where(Rfq.tenant_id == actor.tenant_id, Rfq.id == rfq_id).with_for_update()).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    try:
        check_rfq_transition(r.status, payload.status)
    except SourcingError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    before = r.status
    # VNT-020. `response -> evaluated` used to flip every submitted quote's
    # status and nothing else, so an RFQ could be evaluated with one quote, or
    # with quotes that priced only some of the RFQ's lines, or from suppliers
    # that were never qualified. All four gates are checked here, and the refusal
    # names which one failed — a sourcing control that only says "no" is not a
    # control an auditor can rely on.
    if payload.status == "evaluated":
        _assert_evaluable(db, actor.tenant_id, r)
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


def _assert_evaluable(db: Session, tenant_id: str, r: Rfq) -> None:
    """The bid-evaluation gate. Raises 422 naming the first unmet condition.

    Four independent conditions, each a real procurement control:

    1. **Minimum quote count** — a single bid is not a competitive process.
       `min_quotes` defaults to 1 so an RFQ may deliberately be sole-sourced,
       but it is now an explicit, per-RFQ, recorded number rather than an
       accident of how many suppliers happened to respond.
    2. **Quote completeness** — every RFQ line must be priced by at least one
       quote. A quote that omitted `rfq_line_id` entirely used to be accepted
       (`QuoteLine.rfq_line_id` defaults to ""), and the omission was invisible
       to evaluation.
    3. **Currency consistency** — see VNT-021; a mixed-currency comparison is
       meaningless and the savings figure derived from it is fabricated.
    4. **Supplier eligibility** — a quote from a supplier that is not qualified
       is not a bid. `submit_quote` now refuses such a bid outright, so this
       re-checks the invariant at evaluation rather than trusting it: a row
       inserted by a migration, a script, or an older release must not slip a
       disqualified supplier into an award.
    """
    quotes = list(db.execute(select(Quote).where(
        Quote.tenant_id == tenant_id, Quote.rfq_id == r.id,
        Quote.status.in_(("submitted", "evaluated")))).scalars())
    eligible: list[Quote] = []
    for q in quotes:
        sup = db.get(Supplier, q.supplier_id)
        qualified = db.execute(select(func.count(SupplierQualification.id)).where(
            SupplierQualification.tenant_id == tenant_id, SupplierQualification.supplier_id == q.supplier_id,
            SupplierQualification.status == "qualified")).scalar_one()
        if qualified and sup is not None and sup.status == "active":
            eligible.append(q)

    min_quotes = max(1, int(getattr(r, "min_quotes", 1) or 1))
    if len(eligible) < min_quotes:
        raise HTTPException(status_code=422, detail={
            "code": "RFQ_TOO_FEW_ELIGIBLE_QUOTES",
            "message": f"Evaluation needs at least {min_quotes} eligible quote(s); "
                       f"{len(eligible)} of {len(quotes)} received bid(s) qualify",
            "details": {"received": len(quotes), "eligible": len(eligible), "required": min_quotes}})
    if len(eligible) != len(quotes):
        raise HTTPException(status_code=422, detail={
            "code": "RFQ_SUPPLIER_INELIGIBLE",
            "message": f"{len(quotes) - len(eligible)} bid(s) came from a blocked or unqualified supplier",
            "details": {"supplierIds": sorted({q.supplier_id for q in quotes if q not in eligible})[:20]}})

    rfq_line_ids = [ln.id for ln in db.execute(select(RfqLine).where(
        RfqLine.tenant_id == tenant_id, RfqLine.rfq_id == r.id)).scalars()]
    priced: set[str] = set()
    if rfq_line_ids:
        for qid, line_id in db.execute(
                select(QuoteLine.quote_id, QuoteLine.rfq_line_id).where(
                    QuoteLine.tenant_id == tenant_id,
                    QuoteLine.quote_id.in_([q.id for q in quotes]))).all():
            if str(line_id) in rfq_line_ids:
                priced.add(str(line_id))
        missing = sorted(set(rfq_line_ids) - priced)
        if missing:
            raise HTTPException(status_code=422, detail={
                "code": "RFQ_LINES_UNPRICED",
                "message": f"{len(missing)} RFQ line(s) were priced by no quote",
                "details": {"unpricedLineIds": missing[:20], "unpricedCount": len(missing)}})

    wrong_currency = sorted({(q.currency or "").upper() for q in quotes} - {(r.currency or "").upper()})
    if wrong_currency:
        raise HTTPException(status_code=422, detail={
            "code": "RFQ_CURRENCY_MISMATCH",
            "message": f"Quotes are not in the RFQ currency {r.currency}",
            "details": {"rfqCurrency": r.currency, "quoteCurrencies": wrong_currency}})


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
    # VNT-020. Eligibility belongs at bid *submission*, not only at evaluation.
    # Checking it at evaluation meant the whole evaluation was blocked by one
    # ineligible bid; checking it here means the bid never enters the comparison
    # set in the first place, which is what a supplier-qualification regime
    # actually promises. `blocked` and `on_hold` are explicit non-bidding states.
    if sup.status != "active":
        raise HTTPException(status_code=422, detail={
            "code": "SUPPLIER_NOT_ACTIVE",
            "message": f"Supplier is {sup.status}; only active suppliers may bid",
            "details": {"supplierId": sup.id, "status": sup.status}})
    if not db.execute(select(func.count(SupplierQualification.id)).where(
            SupplierQualification.tenant_id == actor.tenant_id,
            SupplierQualification.supplier_id == sup.id,
            SupplierQualification.status == "qualified")).scalar_one():
        raise HTTPException(status_code=422, detail={
            "code": "SUPPLIER_NOT_QUALIFIED",
            "message": "Supplier holds no approved qualification and may not bid",
            "details": {"supplierId": sup.id}})
    # A quote line must point at a line of *this* RFQ. Unvalidated, a quote could
    # cite an arbitrary (or another tenant's) rfq_line id, and since award totals
    # and savings are derived from these lines, that poisons the money chain.
    rfq_line_ids = [ln.id for ln in db.execute(select(RfqLine).where(
        RfqLine.tenant_id == actor.tenant_id, RfqLine.rfq_id == rfq_id)).scalars()]
    for ln in payload.lines:
        # VNT-020/VNT-021. `rfq_line_id` used to be optional (`if ... and not in`),
        # and `QuoteLine.rfq_line_id` defaults to "". A quote could therefore be
        # submitted with no line mapping at all and still be awarded, which made
        # the RFQ line-coverage gate unverifiable. It is now mandatory, and the
        # currency is asserted equal to the RFQ's rather than merely defaulting to
        # it: a USD quote on an INR RFQ used to rank against INR totals and could
        # be awarded with a fabricated INR savings figure.
        if (ln.rfq_line_id or "").strip() not in rfq_line_ids:
            raise HTTPException(status_code=422, detail={
                "code": "QUOTE_LINE_NOT_ON_RFQ",
                "message": "every lines[].rfq_line_id is required and must reference a line of this RFQ",
                "details": {"rfqLineId": ln.rfq_line_id, "rfqId": rfq_id},
            })
    quote_currency = (payload.currency or r.currency).strip().upper()
    if quote_currency != (r.currency or "").strip().upper():
        raise HTTPException(status_code=422, detail={
            "code": "QUOTE_CURRENCY_MISMATCH",
            "message": f"A quote on this RFQ must be in {r.currency}, not {quote_currency}",
            "details": {"rfqCurrency": r.currency, "quoteCurrency": quote_currency},
        })
    q = Quote(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, rfq_id=rfq_id,
              supplier_id=payload.supplier_id, status="submitted", currency=quote_currency)
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
    # VNT-019. Two changes, both required:
    #   1. lock the RFQ row, so two awarders serialise instead of both clearing
    #      the `exists` pre-check below;
    #   2. wrap the flush in the same `IntegrityError -> 409` pattern every other
    #      route in this file already uses (lines 131 and 210). The award's
    #      `uq_award_tenant_rfq` is the real authority; before, the loser of the
    #      race got an unhandled IntegrityError, which `install_error_handlers`
    #      turned into a 500. A duplicate award is a 409, not a server fault.
    r = db.execute(select(Rfq).where(Rfq.tenant_id == actor.tenant_id, Rfq.id == rfq_id).with_for_update()).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    exists = db.execute(select(Award).where(Award.tenant_id == actor.tenant_id, Award.rfq_id == rfq_id)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="RFQ already awarded")
    if r.status != "evaluated":
        raise HTTPException(status_code=422, detail="RFQ must be evaluated before award")
    # Qualification and quote completeness can change after evaluation. Re-run
    # the gate under the RFQ lock so an award cannot rely on stale eligibility.
    _assert_evaluable(db, actor.tenant_id, r)
    q = db.execute(select(Quote).where(Quote.tenant_id == actor.tenant_id, Quote.id == payload.quote_id, Quote.rfq_id == rfq_id)).scalar_one_or_none()
    if q is None:
        raise HTTPException(status_code=422, detail="Quote does not belong to this RFQ")
    if q.status != "evaluated":
        raise HTTPException(status_code=422, detail="Only an evaluated quote can be awarded")
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
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={
            "code": "RFQ_ALREADY_AWARDED",
            "message": "This RFQ was awarded by a concurrent request"}) from exc
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
    names = supplier_names(db, actor.tenant_id, {q.supplier_id})
    return envelope({"id": a.id, "rfqId": rfq_id, "quoteId": q.id, "supplierId": q.supplier_id,
                     "supplierName": names.get(q.supplier_id, ""), "awardedTotalMinor": server_total},
                    None, getattr(request.state, "request_id", ""))


class OptimizeIn(BaseModel):
    max_share_bp: int = Field(default=10_000, ge=1, le=10_000)
    exclude: list[str] = Field(default_factory=list)


@router.post("/rfqs/{rfq_id}/optimize")
def optimize(rfq_id: str, payload: OptimizeIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """06 optimizer: cheapest feasible split across evaluated quotes (read-only)."""
    from ..services.optimizer import OptimizerError, allocate

    # The allocation itself is not persisted, but this is not a read: it writes an
    # audit event, and it is the most decision-shaped call in the module - it picks
    # which suppliers win a buy. Every other sourcing endpoint that commits
    # anything goes through `_write`, so this one does too. Ungated, any tenant
    # member could enumerate RFQs and harvest the optimizer's recommendation for
    # each, which is the input to a sourcing decision they have no role to make.
    _write(actor)
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
    names = supplier_names(db, actor.tenant_id, {a["supplier_id"] for a in out["allocations"]})
    for a in out["allocations"]:
        a["supplier_name"] = names.get(a["supplier_id"], "")
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="RFQ_OPTIMIZED", resource="rfq",
                 resource_id=rfq_id, after={"total_minor": out["total_minor"], "legs": len(out["allocations"])}, source="api", created_by=actor.sub)
    db.commit()
    return envelope(out, None, getattr(request.state, "request_id", ""))
