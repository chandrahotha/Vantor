"""Purchase API — requisition → PO → receipt → invoice → approval with 3-way match.

- Requisitions: create with lines, submit, approve (SoD) → ordered.
- POs: create from supplier, approve (tiered), send, lines immutable after send.
- Receipts: record against PO lines (cumulative qty guard).
- Invoices: create against PO, lines reference PO lines; approve runs the
  server-side 3-way match (PO ↔ receipt ↔ invoice) — mismatches 422 with detail.
- Approvals: requested → approved/rejected per tier; requester ≠ approver.
- Audit on every state change. All lists premium-grid paginated.
"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.purchase import Approval, Invoice, InvoiceLine, PurchaseOrder, PurchaseOrderLine, Receipt, ReceiptLine, Requisition, RequisitionLine
from ..models.spend import SpendTransaction
from ..models.supplier import Category, Supplier
from ..services.audit import record_event
from ..services.refs import require_ref
from ..services.purchase import APPROVER_ROLES, PurchaseError, check_sod, decide_approval, next_pending, order_pending, required_tiers, three_way_match

router = APIRouter(tags=["purchase"])
WRITE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer", "Finance Reviewer", "Approver"}


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _write(actor: Actor) -> None:
    # Fail-closed: empty/missing roles can never write.
    if not set(actor.roles or ()) & WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for purchase write")


class ReqLineIn(BaseModel):
    description: str = Field(min_length=2, max_length=500)
    quantity: int = Field(ge=1)
    est_price_minor: int = Field(default=0, ge=0)


class ReqIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    title: str = Field(min_length=2, max_length=300)
    notes: str = ""
    lines: list[ReqLineIn] = Field(default_factory=list)


class PoLineIn(BaseModel):
    description: str = Field(min_length=2, max_length=500)
    quantity: int = Field(ge=1)
    unit_price_minor: int = Field(ge=1)


class PoIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    supplier_id: str = Field(min_length=1)
    currency: str = ""
    category_id: str = ""
    lines: list[PoLineIn] = Field(min_length=1)


class ReceiptLineIn(BaseModel):
    po_line_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)


class ReceiptIn(BaseModel):
    notes: str = ""
    lines: list[ReceiptLineIn] = Field(min_length=1)


class InvLineIn(BaseModel):
    po_line_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    unit_price_minor: int = Field(ge=1)


class InvIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    currency: str = ""
    lines: list[InvLineIn] = Field(min_length=1)


def _page(request: Request, rows: list, limit: int) -> dict:
    has_more = len(rows) > limit
    rows = rows[:limit]
    return envelope(rows, {"limit": limit, "nextCursor": rows[-1]["id"] if has_more and rows else "", "hasMore": has_more}, getattr(request.state, "request_id", ""))


@router.get("/requisitions")
def list_reqs(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
              limit: int = Query(default=25, ge=1, le=100), status_: str = Query(default="", alias="status"),
              search: str = Query(default=""), cursor: str = Query(default="")) -> dict:
    """Requisition index. Status + title/code search, cursor-paginated.

    The requisition feature was previously write-only — there was no way to
    list what had been created, which made the UI walk and the acceptance of
    `REQUISITION_CREATED` unverifiable without SQL.
    """
    stmt = select(Requisition).where(Requisition.tenant_id == actor.tenant_id)
    if status_:
        stmt = stmt.where(Requisition.status == status_)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Requisition.title.ilike(like), Requisition.code.ilike(like)))
    if cursor:
        cur = db.execute(select(Requisition).where(Requisition.tenant_id == actor.tenant_id, Requisition.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(Requisition.created_at < cur.created_at,
                              ((Requisition.created_at == cur.created_at) & (Requisition.id < cursor))))
    stmt = stmt.order_by(Requisition.created_at.desc(), Requisition.id.desc()).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    data = [{"id": r.id, "code": r.code, "title": r.title, "status": r.status,
             "requester": r.requester, "createdAt": r.created_at.isoformat() if r.created_at else ""} for r in rows]
    return _page(request, data, limit)


@router.post("/requisitions", status_code=201)
def create_req(payload: ReqIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    r = Requisition(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                    code=payload.code.strip().upper(), title=payload.title.strip(), status="draft", requester=actor.sub, notes=payload.notes.strip())
    db.add(r)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Requisition code exists") from exc
    for i, ln in enumerate(payload.lines, 1):
        db.add(RequisitionLine(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                               requisition_id=r.id, line_no=i, description=ln.description.strip(), quantity=ln.quantity, est_price_minor=ln.est_price_minor))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="REQUISITION_CREATED", resource="requisition", resource_id=r.id, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(r)
    return envelope({"id": r.id, "code": r.code}, None, getattr(request.state, "request_id", ""))


@router.post("/requisitions/{rid}/submit", status_code=200)
def submit_req(rid: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    r = db.execute(select(Requisition).where(Requisition.tenant_id == actor.tenant_id, Requisition.id == rid)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Requisition not found")
    if r.status != "draft":
        raise HTTPException(status_code=422, detail="Only draft requisitions can be submitted")
    r.status = "submitted"
    for t in required_tiers(sum(l.est_price_minor * l.quantity for l in db.execute(select(RequisitionLine).where(RequisitionLine.tenant_id == actor.tenant_id, RequisitionLine.requisition_id == rid)).scalars())):
        db.add(Approval(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, resource="requisition", resource_id=rid, status="requested", tier=t))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="REQUISITION_SUBMITTED", resource="requisition", resource_id=rid, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": rid, "status": "submitted"}, None, getattr(request.state, "request_id", ""))


@router.post("/purchase-orders", status_code=201)
def create_po(payload: PoIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    sup = db.execute(select(Supplier).where(Supplier.tenant_id == actor.tenant_id, Supplier.id == payload.supplier_id)).scalar_one_or_none()
    if sup is None:
        raise HTTPException(status_code=422, detail="Unknown supplier")
    total = sum(l.unit_price_minor * l.quantity for l in payload.lines)
    # "" means "uncategorised" and is allowed; anything else must be a real
    # category, because an uncategorised PO both bypasses the budget gate and
    # trips the maverick report.
    category_id = require_ref(db, Category, actor.tenant_id, payload.category_id, field="category_id", code="UNKNOWN_CATEGORY")
    po = PurchaseOrder(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                       code=payload.code.strip().upper(), supplier_id=payload.supplier_id, status="draft",
                       currency=payload.currency.strip().upper(), total_minor=total, category_id=category_id)
    db.add(po)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="PO code exists") from exc
    for i, ln in enumerate(payload.lines, 1):
        db.add(PurchaseOrderLine(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, po_id=po.id, line_no=i,
                                 description=ln.description.strip(), quantity=ln.quantity, unit_price_minor=ln.unit_price_minor, line_total_minor=ln.unit_price_minor * ln.quantity))
    for t in required_tiers(total):
        db.add(Approval(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, resource="purchase_order", resource_id=po.id, status="requested", tier=t))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PO_CREATED", resource="purchase_order", resource_id=po.id, after={"total_minor": total}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(po)
    return envelope({"id": po.id, "totalMinor": total, "tiers": required_tiers(total)}, None, getattr(request.state, "request_id", ""))


@router.get("/approvals")
def list_approvals(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
                   limit: int = Query(default=25, ge=1, le=100),
                   status_: str = Query(default="requested", alias="status"),
                   resource: str = Query(default=""), tier: str = Query(default=""),
                   cursor: str = Query(default="")) -> dict:
    """The approval queue — the read side of the HITL loop.

    Approvals were write-only: rows were filed by PO/requisition/invoice/AI
    paths and nothing could list them, so the queue only existed in SQL. Roles
    come from the verified token, so a tenant can only ever see its own rows.
    """
    if not set(actor.roles or ()) & APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="Approver role required to view the approval queue")
    stmt = select(Approval).where(Approval.tenant_id == actor.tenant_id)
    if status_:
        stmt = stmt.where(Approval.status == status_)
    if resource:
        stmt = stmt.where(Approval.resource == resource)
    if tier:
        stmt = stmt.where(Approval.tier == tier)
    if cursor:
        cur = db.execute(select(Approval).where(Approval.tenant_id == actor.tenant_id, Approval.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(Approval.created_at < cur.created_at,
                              ((Approval.created_at == cur.created_at) & (Approval.id < cursor))))
    stmt = stmt.order_by(Approval.created_at.desc(), Approval.id.desc()).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more = len(rows) > limit
    rows = rows[:limit]
    data = [{
        "id": a.id, "resource": a.resource, "resourceId": a.resource_id, "status": a.status,
        "tier": a.tier, "requestedBy": a.created_by, "decidedBy": a.decided_by or "",
        "reason": a.reason or "", "requiresHumanReview": True,
        "createdAt": a.created_at.isoformat() if a.created_at else "",
    } for a in rows]
    return envelope(data, {"limit": limit, "nextCursor": data[-1]["id"] if has_more and data else "",
                           "hasMore": has_more}, getattr(request.state, "request_id", ""))


class DecideIn(BaseModel):
    approve: bool = False
    reason: str = Field(default="", max_length=1000)


@router.post("/approvals/{aid}/decide", status_code=200)
def decide_approval_endpoint(aid: str, payload: DecideIn, request: Request, actor: Actor = Depends(get_actor),
                             db: Session = Depends(db_for_actor)) -> dict:
    """Decide one approval (requisition, purchase order, invoice).

    `ai:*` approvals are deliberately excluded: they are decided through
    `/ai/approvals/{id}/decide` so the copilot's HITL path stays explicit.
    Nothing auto-executes on approval — the caller then acts through the
    normal endpoint.
    """
    _write(actor)
    row = db.execute(select(Approval).where(Approval.tenant_id == actor.tenant_id, Approval.id == aid)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if row.resource.startswith("ai:"):
        raise HTTPException(status_code=422, detail="AI approvals are decided through /ai/approvals/{id}/decide")
    try:
        new_status = decide_approval(db, tenant_id=actor.tenant_id, approver_sub=actor.sub,
                                     approver_roles=set(actor.roles or ()), approval=row,
                                     approve=payload.approve, reason=payload.reason)
    except PurchaseError as exc:
        raise HTTPException(status_code=_approval_status(exc.code), detail={"code": exc.code, "message": exc.message}) from exc
    parent_status = _sync_parent(db, actor.tenant_id, row)
    db.commit()
    return envelope({"id": aid, "status": new_status, "resource": row.resource,
                     "resourceId": row.resource_id, "resourceStatus": parent_status},
                    None, getattr(request.state, "request_id", ""))


def _approval_status(code: str) -> int:
    return {"APPROVAL_ROLE": 403, "APPROVAL_SOD": 403, "APPROVAL_ALREADY_DECIDED": 409,
            "APPROVAL_REASON_REQUIRED": 422}.get(code, 422)


def _sync_parent(db: Session, tenant_id: str, approval: Approval) -> str:
    """Push the decision onto the document the approval was filed against.

    This is what closes the requisition dead-end: a submitted requisition had
    approvals nothing could decide, so it could never leave `submitted`. The
    transition only fires from the state the document is actually parked in
    while it waits for approval, so a PO already sent can never be dragged back
    to `rejected` by a late decision.
    """
    model, status_attr, awaiting = {
        "requisition": (Requisition, "status", "submitted"),
        "purchase_order": (PurchaseOrder, "status", "draft"),
        "invoice": (Invoice, "status", "received"),
    }.get(approval.resource, (None, "", ""))
    if model is None:
        return ""
    if approval.status == "rejected":
        decision = "rejected"
    else:
        siblings = list(db.execute(select(Approval).where(
            Approval.tenant_id == tenant_id, Approval.resource == approval.resource,
            Approval.resource_id == approval.resource_id)).scalars())
        decision = "approved" if all(a.status == "approved" for a in siblings) else ""
    if not decision:
        return ""
    # Every model here is a TenantMixin subclass, so `tenant_id`/`id` exist; the
    # mapping is built from literals above, so the union is not worth modelling.
    parent = db.execute(select(model).where(  # type: ignore[attr-defined]
        model.tenant_id == tenant_id, model.id == approval.resource_id  # type: ignore[attr-defined]
    )).scalar_one_or_none()
    if parent is None:
        return ""
    current = getattr(parent, status_attr, "")
    if current != awaiting:
        return current
    setattr(parent, status_attr, decision)
    setattr(parent, "updated_by", approval.decided_by or approval.updated_by or "")
    return decision


@router.post("/purchase-orders/{pid}/approve", status_code=200)
def approve_po(pid: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid)).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status != "draft":
        raise HTTPException(status_code=422, detail="Only draft POs can be approved")
    try:
        check_sod(po.created_by, actor.sub)
    except PurchaseError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    pend = list(db.execute(select(Approval).where(Approval.tenant_id == actor.tenant_id, Approval.resource == "purchase_order", Approval.resource_id == pid, Approval.status == "requested")).scalars())
    if not pend:
        raise HTTPException(status_code=422, detail="No pending approvals")
    # Hard budget gate before any approval lands (Ariba-style real-time check).
    from ..routers.catalog import check_budget as _check_budget

    _check_budget(db, tenant_id=actor.tenant_id, category_id=po.category_id, this_total=po.total_minor, currency=po.currency)
    # Clear the *earliest* outstanding tier. Reading `pend[0]` off an unordered
    # result let a finance approver consume the manager's slot and skip a step.
    step = next_pending(pend)
    step.status, step.decided_by = "approved", actor.sub
    if all(a.status == "approved" for a in db.execute(select(Approval).where(Approval.tenant_id == actor.tenant_id, Approval.resource == "purchase_order", Approval.resource_id == pid)).scalars()):
        po.status = "approved"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PO_APPROVED", resource="purchase_order", resource_id=pid, after={"tier": step.tier}, source="api", created_by=actor.sub)
    from ..services.notify import notify as _notify

    _notify(db, tenant_id=actor.tenant_id, kind="PO_APPROVED", title=f"PO {po.code} approved ({step.tier})",
            link="/orders", user_sub=po.created_by, created_by=actor.sub)
    db.commit()
    return envelope({"id": pid, "status": po.status, "tier": step.tier,
                     "pending": [a.tier for a in order_pending(list(db.execute(select(Approval).where(
                         Approval.tenant_id == actor.tenant_id, Approval.resource == "purchase_order",
                         Approval.resource_id == pid, Approval.status == "requested")).scalars()))]},
                    None, getattr(request.state, "request_id", ""))


@router.post("/purchase-orders/{pid}/send", status_code=200)
def send_po(pid: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid)).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status != "approved":
        raise HTTPException(status_code=422, detail="Only approved POs can be sent")
    po.status = "sent"
    db.add(SpendTransaction(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                            kind="commitment", po_id=pid, supplier_id=po.supplier_id,
                            currency=po.currency, amount_minor=po.total_minor))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PO_SENT", resource="purchase_order", resource_id=pid, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": pid, "status": "sent"}, None, getattr(request.state, "request_id", ""))


@router.post("/purchase-orders/{pid}/receipts", status_code=201)
def receive(pid: str, payload: ReceiptIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid)).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status not in {"sent", "received"}:
        raise HTTPException(status_code=422, detail="PO must be sent before receiving")
    po_line_ids = {l.id: l for l in db.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.tenant_id == actor.tenant_id, PurchaseOrderLine.po_id == pid)).scalars()}
    # Cumulative received per PO line (all prior receipts) — over-receipt is 422.
    # One grouped query for the whole PO; this used to issue a query per prior
    # receipt, so a PO with many deliveries cost O(receipts) round trips.
    prior: dict[str, int] = {}
    receipt_ids = [r for r in db.execute(select(Receipt.id).where(Receipt.tenant_id == actor.tenant_id, Receipt.po_id == pid)).scalars()]
    if receipt_ids:
        for line_id, qty in db.execute(
                select(ReceiptLine.po_line_id, func.coalesce(func.sum(ReceiptLine.quantity), 0))
                .where(ReceiptLine.tenant_id == actor.tenant_id, ReceiptLine.receipt_id.in_(receipt_ids))
                .group_by(ReceiptLine.po_line_id)).all():
            prior[line_id] = int(qty)
    r = Receipt(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, po_id=pid, received_by=actor.sub, notes=payload.notes)
    db.add(r)
    db.flush()
    for ln in payload.lines:
        pl = po_line_ids.get(ln.po_line_id)
        if pl is None:
            raise HTTPException(status_code=422, detail="Receipt line references unknown PO line")
        if prior.get(ln.po_line_id, 0) + ln.quantity > pl.quantity:
            raise HTTPException(status_code=422, detail=f"Over-receipt on PO line {pl.line_no}: ordered {pl.quantity}, already received {prior.get(ln.po_line_id, 0)}")
        db.add(ReceiptLine(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, receipt_id=r.id, po_line_id=ln.po_line_id, quantity=ln.quantity))
    po.status = "received"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PO_RECEIVED", resource="purchase_order", resource_id=pid, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": r.id}, None, getattr(request.state, "request_id", ""))


@router.post("/purchase-orders/{pid}/invoices", status_code=201)
def create_invoice(pid: str, payload: InvIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid)).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    # An invoice line must cite a line of *this* PO. Unvalidated, the bad id was
    # stored and only surfaced later as a three-way-match failure at approval
    # time — the write accepted a record that could never be paid.
    po_line_ids = {l.id for l in db.execute(select(PurchaseOrderLine).where(
        PurchaseOrderLine.tenant_id == actor.tenant_id, PurchaseOrderLine.po_id == pid)).scalars()}
    for ln in payload.lines:
        if (ln.po_line_id or "").strip() not in po_line_ids:
            raise HTTPException(status_code=422, detail={
                "code": "INVOICE_LINE_NOT_ON_PO",
                "message": "lines[].po_line_id must reference a line of this purchase order",
                "details": {"poLineId": ln.po_line_id, "poId": pid},
            })
    total = sum(l.unit_price_minor * l.quantity for l in payload.lines)
    inv = Invoice(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, code=payload.code.strip().upper(),
                  po_id=pid, supplier_id=po.supplier_id, status="received", currency=(payload.currency or po.currency).strip().upper(), total_minor=total)
    db.add(inv)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Invoice code exists") from exc
    for ln in payload.lines:
        db.add(InvoiceLine(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, invoice_id=inv.id,
                           po_line_id=ln.po_line_id, quantity=ln.quantity, unit_price_minor=ln.unit_price_minor, line_total_minor=ln.unit_price_minor * ln.quantity))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="INVOICE_RECEIVED", resource="invoice", resource_id=inv.id, after={"total_minor": total}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(inv)
    return envelope({"id": inv.id, "totalMinor": total}, None, getattr(request.state, "request_id", ""))


@router.post("/invoices/{iid}/approve", status_code=200)
def approve_invoice(iid: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    inv = db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.id == iid)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status != "received":
        raise HTTPException(status_code=422, detail="Only received invoices can be approved")
    try:
        check_sod(inv.created_by, actor.sub)
        detail = three_way_match(db, tenant_id=actor.tenant_id, po_id=inv.po_id, invoice_id=iid)
    except PurchaseError as exc:
        code = 403 if exc.code == "APPROVAL_SOD" else 422
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message, "details": exc.details}) from exc
    inv.status = "approved"
    db.add(SpendTransaction(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                            kind="actual", po_id=inv.po_id, invoice_id=iid, supplier_id=inv.supplier_id,
                            currency=inv.currency, amount_minor=inv.total_minor))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="INVOICE_APPROVED", resource="invoice",
                 resource_id=iid, after={"matched": detail}, source="api", created_by=actor.sub)
    from ..services.notify import notify as _notify2

    _notify2(db, tenant_id=actor.tenant_id, kind="INVOICE_APPROVED", title=f"Invoice {inv.code} approved (3-way matched)",
             link="/orders", user_sub=inv.created_by, created_by=actor.sub)
    db.commit()
    return envelope({"id": iid, "status": "approved", "matched": detail}, None, getattr(request.state, "request_id", ""))


@router.get("/purchase-orders")
def list_pos(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
             limit: int = Query(default=25, ge=1, le=100), cursor: str = Query(default=""), status_: str = Query(default="", alias="status")) -> dict:
    stmt = select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id)
    if status_:
        stmt = stmt.where(PurchaseOrder.status == status_)
    if cursor:
        cur = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(PurchaseOrder.created_at < cur.created_at,
                              ((PurchaseOrder.created_at == cur.created_at) & (PurchaseOrder.id < cursor))))
    stmt = stmt.order_by(desc(PurchaseOrder.created_at), desc(PurchaseOrder.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more, rows = len(rows) > limit, rows[:limit]
    data = [{"id": p.id, "code": p.code, "status": p.status, "totalMinor": p.total_minor, "supplierId": p.supplier_id} for p in rows]
    return envelope(data, {"limit": limit, "nextCursor": rows[-1].id if has_more and rows else "", "hasMore": has_more}, getattr(request.state, "request_id", ""))


@router.get("/purchase-orders/{pid}")
def get_po(pid: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid)).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    lines = list(db.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.tenant_id == actor.tenant_id, PurchaseOrderLine.po_id == pid).order_by(PurchaseOrderLine.line_no)).scalars())
    invs = list(db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.po_id == pid)).scalars())
    return envelope({"id": po.id, "code": po.code, "status": po.status, "totalMinor": po.total_minor,
                     "supplierId": po.supplier_id, "currency": po.currency,
                     "lines": [{"id": l.id, "lineNo": l.line_no, "description": l.description, "quantity": l.quantity,
                                "unitPriceMinor": l.unit_price_minor, "lineTotalMinor": l.line_total_minor} for l in lines],
                     "invoices": [{"id": i.id, "code": i.code, "status": i.status} for i in invs]},
                    None, getattr(request.state, "request_id", ""))
