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
from ..services.names import supplier_names
from ..services.refs import require_ref
from ..services.purchase import APPROVER_ROLES, PurchaseError, check_sod, decide_approval, next_pending, order_pending, required_tiers, three_way_match

router = APIRouter(tags=["purchase"])
WRITE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer", "Finance Reviewer", "Approver"}

#: The purchase-order lifecycle, in one place. VNT-018: `PO_STATUSES` listed
#: seven states and nothing enforced the edges — three of them (`invoiced`,
#: `closed`, `cancelled`) had no writer at all, so they were unreachable in
#: practice while the workkit's PURCHASE_ORDER.md described transitions between
#: them. Every command below now reads its allowed successors from here, and the
#: DB CHECK constraint renders the same domain, so the model, the API and the
#: schema cannot disagree about what a PO may be.
PO_FLOW: dict[str, set[str]] = {
    "draft": {"approved", "cancelled"},
    "approved": {"sent", "cancelled"},
    "sent": {"received", "cancelled"},
    "received": {"invoiced", "cancelled"},
    "invoiced": {"closed"},
    "closed": set(),
    "cancelled": set(),
}

#: Invoice lifecycle. `matched` is the state a clean three-way match parks an
#: invoice in before payment is authorised; it is a real transition, not a
#: bookkeeping label, so the audit trail can distinguish "failed the match" from
#: "matched but not yet approved".
INVOICE_FLOW: dict[str, set[str]] = {
    "received": {"matched", "approved", "rejected"},
    "matched": {"approved", "rejected"},
    "approved": {"paid", "rejected"},
    "paid": set(),
    "rejected": {"received"},  # re-submitted after correction
}


def _check_invoice_transition(old: str, new: str) -> None:
    """Refuse an invoice transition the declared lifecycle does not allow.

    This was a decoration. `INVOICE_FLOW` and `INVOICE_STATUSES` were checked by
    a test that only compared the two against each other, and the status CHECK
    constraint listed `matched`, so all three agreed that `matched` existed — but
    no code path ever read `INVOICE_FLOW`, and `matched` had no writer. A test
    that compares a declaration with another declaration proves the declarations
    agree, not that anything obeys them.
    """
    if new not in INVOICE_FLOW.get(old, set()):
        allowed = sorted(INVOICE_FLOW.get(old, set())) or ["(terminal)"]
        raise HTTPException(status_code=422, detail={
            "code": "INVOICE_TRANSITION_INVALID",
            "message": f"An invoice in {old!r} cannot move to {new!r}",
            "details": {"from": old, "to": new, "allowed": allowed}})


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _write(actor: Actor) -> None:
    # Fail-closed: empty/missing roles can never write.
    if not set(actor.roles or ()) & WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for purchase write")


def _decide(actor: Actor) -> None:
    """Authority to *decide* a financial control — narrower than write.

    VNT-002 / VNT-003. The direct `approve` routes used to be guarded by
    `WRITE_ROLES`, which contains `Buyer`. A buyer could therefore approve a PO
    or an invoice while being refused `GET /approvals` and
    `POST /approvals/{id}/decide`, because those require `APPROVER_ROLES`, which
    does not. Two live implementations of one policy, the wider one on the money
    path. Approval authority is now a distinct capability, checked in exactly
    one place, on every route that moves money forward.
    """
    if not set(actor.roles or ()) & APPROVER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail={"code": "APPROVAL_ROLE",
                                    "message": "An approver role is required to decide a financial control. "
                                               "Write access is not approval authority."})


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
    # A PO may answer a requisition; empty means it was raised directly, which is
    # legitimate (it just shows up correctly in spend intelligence).
    requisition_id: str = ""
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
    # Same for the requisition: empty means the PO was raised directly, a
    # non-empty id has to point at a real requisition in this tenant. Buying
    # against a requisition that does not exist used to create an orphan with
    # the FK in place.
    requisition_id = require_ref(db, Requisition, actor.tenant_id, payload.requisition_id,
                                 field="requisition_id", code="UNKNOWN_REQUISITION")
    po = PurchaseOrder(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                       code=payload.code.strip().upper(), supplier_id=payload.supplier_id, status="draft",
                       currency=payload.currency.strip().upper(), total_minor=total, category_id=category_id,
                       requisition_id=requisition_id or None)
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
    # VNT-018: `ordered` was a dead requisition state. A requisition that had
    # been approved and answered by a real PO now actually reaches the state the
    # workkit's REQUISITION.md describes, which is also what makes "approved but
    # never ordered" a reportable condition rather than an invisible one.
    if requisition_id:
        req = db.execute(select(Requisition).where(
            Requisition.tenant_id == actor.tenant_id, Requisition.id == requisition_id).with_for_update()).scalar_one_or_none()
        if req is not None and req.status == "approved":
            req.status = "ordered"
            record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="REQUISITION_ORDERED",
                         resource="requisition", resource_id=req.id, after={"poId": po.id},
                         source="api", created_by=actor.sub)
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
    # VNT-UI: this queue used to answer "what am I deciding" with the resource
    # type and eight characters of a UUID — the one screen whose entire job is
    # letting a human make an informed approve/reject call showed them the
    # least human-readable identifier in the product. One grouped query per
    # resource type instead of one per row.
    codes: dict[str, str] = {}
    req_ids = {a.resource_id for a in rows if a.resource == "requisition"}
    po_ids = {a.resource_id for a in rows if a.resource == "purchase_order"}
    inv_ids = {a.resource_id for a in rows if a.resource == "invoice"}
    if req_ids:
        codes.update({r.id: r.code for r in db.execute(select(Requisition).where(
            Requisition.tenant_id == actor.tenant_id, Requisition.id.in_(req_ids))).scalars()})
    if po_ids:
        codes.update({p.id: p.code for p in db.execute(select(PurchaseOrder).where(
            PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id.in_(po_ids))).scalars()})
    if inv_ids:
        codes.update({i.id: i.code for i in db.execute(select(Invoice).where(
            Invoice.tenant_id == actor.tenant_id, Invoice.id.in_(inv_ids))).scalars()})
    data = [{
        "id": a.id, "resource": a.resource, "resourceId": a.resource_id,
        "resourceCode": codes.get(a.resource_id, ""), "status": a.status,
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
    _decide(actor)
    # Lock the PO for the whole decision. The budget gate below reads a SUM and
    # this route flips an approval, so two concurrent approvers would both
    # clear the same tier against the same stale read.
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid).with_for_update()).scalar_one_or_none()
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

    # No category => no budget gate applies ("" was the old sentinel — 0018 moved to NULL).
    if po.category_id:
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
    if "sent" not in PO_FLOW.get("approved", set()):  # pragma: no cover - guards the table itself
        raise HTTPException(status_code=500, detail="PO_FLOW is missing approved->sent")
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid).with_for_update()).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status != "approved":
        raise HTTPException(status_code=422, detail="Only approved POs can be sent")
    po.status = "sent"
    db.add(SpendTransaction(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                            kind="commitment", po_id=pid, supplier_id=po.supplier_id,
                            currency=po.currency, amount_minor=po.total_minor))
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PO_SENT", resource="purchase_order", resource_id=pid, source="api", created_by=actor.sub)
    try:
        db.commit()
    except IntegrityError as exc:
        # uq_spend_tenant_kind_po_inv. A second concurrent send of the same PO
        # cannot double-post the commitment; the database refuses it and we say
        # so, instead of a bare 500 from the global handler.
        db.rollback()
        raise HTTPException(status_code=409,
                            detail={"code": "LEDGER_ALREADY_POSTED",
                                    "message": "This purchase order is already posted to the spend ledger"}) from exc
    return envelope({"id": pid, "status": "sent"}, None, getattr(request.state, "request_id", ""))


@router.post("/purchase-orders/{pid}/receipts", status_code=201)
def receive(pid: str, payload: ReceiptIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    # VNT-005. The over-receipt guard is a read of every prior receipt followed
    # by a write, so without a lock two concurrent deliveries both read
    # `prior = 0`, both pass `0 + 10 <= 10`, and the PO ends up with 20 units
    # received against 10 ordered — which then makes every invoice against it
    # pass a cumulative check it should fail. Same lock the invoice path takes,
    # so receipts and approvals serialise against each other per PO.
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid).with_for_update()).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status not in {"sent", "received"}:
        raise HTTPException(status_code=422, detail="PO must be sent before receiving")
    po_line_ids = {l.id: l for l in db.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.tenant_id == actor.tenant_id, PurchaseOrderLine.po_id == pid)).scalars()}
    # Validate every line before inserting anything, so a bad line cannot leave a
    # half-written receipt behind a 422.
    prior: dict[str, int] = {}
    receipt_ids = [r for r in db.execute(select(Receipt.id).where(Receipt.tenant_id == actor.tenant_id, Receipt.po_id == pid)).scalars()]
    if receipt_ids:
        for line_id, qty in db.execute(
                select(ReceiptLine.po_line_id, func.coalesce(func.sum(ReceiptLine.quantity), 0))
                .where(ReceiptLine.tenant_id == actor.tenant_id, ReceiptLine.receipt_id.in_(receipt_ids))
                .group_by(ReceiptLine.po_line_id)).all():
            prior[str(line_id)] = int(qty)
    seen: dict[str, int] = {}
    for ln in payload.lines:
        pl = po_line_ids.get(ln.po_line_id)
        if pl is None:
            raise HTTPException(status_code=422, detail="Receipt line references unknown PO line")
        seen[ln.po_line_id] = seen.get(ln.po_line_id, 0) + ln.quantity
        if prior.get(ln.po_line_id, 0) + seen[ln.po_line_id] > pl.quantity:
            raise HTTPException(status_code=422, detail=f"Over-receipt on PO line {pl.line_no}: ordered {pl.quantity}, already received {prior.get(ln.po_line_id, 0)}")
    r = Receipt(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, po_id=pid, received_by=actor.sub, notes=payload.notes)
    db.add(r)
    db.flush()
    for ln in payload.lines:
        db.add(ReceiptLine(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, receipt_id=r.id, po_line_id=ln.po_line_id, quantity=ln.quantity))
    po.status = "received"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PO_RECEIVED", resource="purchase_order", resource_id=pid, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": r.id}, None, getattr(request.state, "request_id", ""))


class CancelIn(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


@router.post("/purchase-orders/{pid}/cancel", status_code=200)
def cancel_po(pid: str, payload: CancelIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Cancel a PO that has not yet been invoiced.

    VNT-018. `cancelled` was in `PO_STATUSES` with no writer, so a PO that had to
    be abandoned stayed `draft`/`sent` forever and kept its budget reservation
    and approval queue alive. Cancelling releases the approval queue and refuses
    if any invoice is already approved, because reversing a posted `actual` is a
    finance action, not a status write.
    """
    _write(actor)
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid).with_for_update()).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status not in PO_FLOW.get(po.status, set()):
        raise HTTPException(status_code=422, detail={"code": "PO_TRANSITION_INVALID",
                                                     "message": f"A {po.status} purchase order cannot be cancelled",
                                                     "details": {"allowed": sorted(PO_FLOW.get(po.status, set()))}})
    if db.execute(select(func.count(Invoice.id)).where(
            Invoice.tenant_id == actor.tenant_id, Invoice.po_id == pid,
            Invoice.status.in_(("approved", "paid")))).scalar_one():
        raise HTTPException(status_code=409, detail={"code": "PO_HAS_POSTED_ACTUALS",
                                                     "message": "This PO has approved invoices. Reverse the spend ledger before cancelling it."})
    po.status = "cancelled"
    for a in db.execute(select(Approval).where(
            Approval.tenant_id == actor.tenant_id, Approval.resource == "purchase_order",
            Approval.resource_id == pid, Approval.status == "requested")).scalars():
        a.status = "rejected"
        a.decided_by, a.reason, a.updated_by = actor.sub, payload.reason.strip(), actor.sub
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PO_CANCELLED", resource="purchase_order",
                 resource_id=pid, reason=payload.reason.strip(), source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": pid, "status": "cancelled"}, None, getattr(request.state, "request_id", ""))


@router.post("/purchase-orders/{pid}/close", status_code=200)
def close_po(pid: str, payload: CancelIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Close a fully-invoiced PO. VNT-018: `closed` had no writer."""
    _write(actor)
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid).with_for_update()).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.status not in PO_FLOW.get(po.status, set()):
        raise HTTPException(status_code=422, detail={"code": "PO_TRANSITION_INVALID",
                                                     "message": f"A {po.status} purchase order cannot be closed",
                                                     "details": {"allowed": sorted(PO_FLOW.get(po.status, set()))}})
    po.status = "closed"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PO_CLOSED", resource="purchase_order",
                 resource_id=pid, reason=payload.reason.strip(), source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": pid, "status": "closed"}, None, getattr(request.state, "request_id", ""))


@router.post("/invoices/{iid}/match", status_code=200)
def match_invoice(iid: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Run the three-way match and park the invoice in `matched`.

    `matched` was in `INVOICE_STATUSES`, in `INVOICE_FLOW` and in the database
    CHECK constraint, and had no writer at all: approval went straight from
    `received` to `approved`, performing the match inside the same request. Three
    declarations agreed that the state existed, and nothing could put an invoice
    in it, so an auditor asking "was this matched before it was approved, and by
    whom" had no answer — the audit event recorded the match at approval time,
    attributed to the approver rather than to the matcher.

    This makes the state real and separates the two decisions: matching is a
    control, approval is a separate one, and a mismatch is recorded as a failure
    to match rather than as a rejection. The match is re-run on approval, so
    parking an invoice here never lets stale quantities through.
    """
    _decide(actor)
    inv = db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.id == iid).with_for_update()).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status != "received":
        raise HTTPException(status_code=422, detail="Only received invoices can be matched")
    _check_invoice_transition(inv.status, "matched")
    po_id = _require_po_id(inv)
    try:
        check_sod(inv.created_by, actor.sub)
        detail = three_way_match(db, tenant_id=actor.tenant_id, po_id=po_id, invoice_id=iid)
    except PurchaseError as exc:
        code = 403 if exc.code == "APPROVAL_SOD" else 422
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message,
                                                      "details": exc.details}) from exc
    inv.status = "matched"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="INVOICE_MATCHED", resource="invoice",
                 resource_id=iid, after={"matched": detail}, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": iid, "status": "matched", "matched": detail}, None,
                    getattr(request.state, "request_id", ""))


@router.post("/invoices/{iid}/reject", status_code=200)
def reject_invoice(iid: str, payload: CancelIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Reject an invoice, with a written reason, before it is approved.

    VNT-018. `rejected` was in `INVOICE_STATUSES` with no writer, so a match
    failure was terminal and unrecorded: the supplier was never told why, and the
    PO line's received quantity stayed consumed by an invoice nobody could clear.
    Rejecting releases the received quantity, so the same goods can be re-billed
    correctly — which is the whole point of the cumulative check.
    """
    _decide(actor)
    inv = db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.id == iid).with_for_update()).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status not in ("received", "matched"):
        raise HTTPException(status_code=422, detail="Only received or matched invoices can be rejected")
    _check_invoice_transition(inv.status, "rejected")
    try:
        check_sod(inv.created_by, actor.sub)
    except PurchaseError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    inv.status = "rejected"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="INVOICE_REJECTED", resource="invoice",
                 resource_id=iid, reason=payload.reason.strip(), source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": iid, "status": "rejected"}, None, getattr(request.state, "request_id", ""))


@router.post("/invoices/{iid}/pay", status_code=200)
def pay_invoice(iid: str, payload: CancelIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Record payment. VNT-018: `paid` was a dead state — nothing could settle.

    The ledger already carries the liability as an `actual` at approval time, so
    this records settlement *of* that row rather than moving money again. The
    reference is kept because AP reconciliation needs the payment instrument,
    not because the number moves again.
    """
    _decide(actor)
    inv = db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.id == iid).with_for_update()).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status != "approved":
        raise HTTPException(status_code=422, detail="Only approved invoices can be paid")
    _check_invoice_transition(inv.status, "paid")
    inv.status = "paid"
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="INVOICE_PAID", resource="invoice",
                 resource_id=iid, reason=payload.reason.strip(), after={"reference": payload.reason.strip()},
                 source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": iid, "status": "paid"}, None, getattr(request.state, "request_id", ""))


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
    _decide(actor)
    inv = db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.id == iid)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status not in ("received", "matched"):
        raise HTTPException(status_code=422, detail="Only received or matched invoices can be approved")
    _check_invoice_transition(inv.status, "approved")
    po_id = _require_po_id(inv)
    try:
        check_sod(inv.created_by, actor.sub)
        # `three_way_match` locks the PO row and reads every other approved
        # invoice on it, so the cumulative quantity check below is atomic
        # against a concurrent approval of a second invoice for the same PO.
        detail = three_way_match(db, tenant_id=actor.tenant_id, po_id=po_id, invoice_id=iid)
    except PurchaseError as exc:
        code = 403 if exc.code == "APPROVAL_SOD" else 422
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message, "details": exc.details}) from exc
    inv.status = "approved"
    db.add(SpendTransaction(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                            kind="actual", po_id=inv.po_id, invoice_id=iid, supplier_id=inv.supplier_id,
                            currency=inv.currency, amount_minor=inv.total_minor))
    # VNT-033: a business counter, because "every request is 200" and "procurement
    # is working" are different questions. A deployment where money stopped being
    # posted would otherwise look perfectly healthy.
    try:
        from ..core.observe import incr

        incr("vantor_money_posted", inv.currency, "actual")
    except Exception:  # noqa: BLE001 - telemetry is never load-bearing
        pass
    # The PO is `invoiced` only once the goods are fully billed. Determined
    # inside the same locked transaction as the match, so a second invoice on the
    # same PO cannot also claim the PO. VNT-018: this state had no writer at all,
    # so the dashboard's "awaiting payment" filter matched nothing ever.
    _mark_po_invoiced(db, actor, po_id, iid)
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="INVOICE_APPROVED", resource="invoice",
                 resource_id=iid, after={"matched": detail}, source="api", created_by=actor.sub)
    from ..services.notify import notify as _notify2

    _notify2(db, tenant_id=actor.tenant_id, kind="INVOICE_APPROVED", title=f"Invoice {inv.code} approved (3-way matched)",
             link="/orders", user_sub=inv.created_by, created_by=actor.sub)
    try:
        db.commit()
    except IntegrityError as exc:
        # uq_spend_tenant_kind_po_inv: another approval of this same invoice
        # committed first. The ledger refuses the second write; say so plainly
        # rather than surfacing a 500.
        db.rollback()
        raise HTTPException(status_code=409,
                            detail={"code": "LEDGER_ALREADY_POSTED",
                                    "message": "This invoice is already posted to the spend ledger"}) from exc
    return envelope({"id": iid, "status": "approved", "matched": detail}, None, getattr(request.state, "request_id", ""))


def _require_po_id(inv: Invoice) -> str:
    """The PO an invoice is matched against, or a 422 that says why not.

    `invoices.po_id` is nullable — the migration allows NULL and a draft
    invoice can legitimately have no PO yet — while `three_way_match` and
    `_mark_po_invoiced` both take a `str`. Nothing enforced that at the call
    site, so the type was wrong and the runtime behaviour was accidentally
    safe: `PurchaseOrder.id == None` renders as `id IS NULL`, matches no row,
    and the match failed with `MATCH_NO_PO "Purchase order None not found"`.

    That is a 422 for the wrong reason, naming an id the caller never sent, on
    the one path in the product whose job is to decide whether an invoice may
    become money. The invariant is now stated where it is relied on.
    """
    if inv.po_id is None:
        raise HTTPException(status_code=422, detail={"code": "INVOICE_NO_PO",
                                                     "message": "Invoice is not linked to a purchase order",
                                                     "details": {"invoiceId": inv.id}})
    return inv.po_id


def _mark_po_invoiced(db: Session, actor: Actor, po_id: str, invoice_id: str) -> bool:
    """Advance the PO to `invoiced` once every ordered unit is approved-billed.

    Returns whether it moved. Cumulative *approved* quantity is compared against
    ordered quantity, mirroring the match that just passed, so a partially
    invoiced PO correctly stays `received`.
    """
    from sqlalchemy import func as _f

    po = db.execute(select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == po_id)).scalar_one_or_none()
    if po is None or po.status != "received":
        return False
    ordered = {l.id: l.quantity for l in db.execute(select(PurchaseOrderLine).where(
        PurchaseOrderLine.tenant_id == actor.tenant_id, PurchaseOrderLine.po_id == po_id)).scalars()}
    if not ordered:
        return False
    billed: dict[str, int] = {}
    approved_ids = list(db.execute(select(Invoice.id).where(
        Invoice.tenant_id == actor.tenant_id, Invoice.po_id == po_id,
        Invoice.status.in_(("approved", "paid")))).scalars())
    if approved_ids:
        for line_id, qty in db.execute(
                select(InvoiceLine.po_line_id, _f.coalesce(_f.sum(InvoiceLine.quantity), 0))
                .where(InvoiceLine.tenant_id == actor.tenant_id, InvoiceLine.invoice_id.in_(approved_ids))
                .group_by(InvoiceLine.po_line_id)).all():
            billed[str(line_id)] = int(qty)
    if all(billed.get(line_id, 0) >= qty for line_id, qty in ordered.items()):
        po.status = "invoiced"
        record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PO_INVOICED",
                     resource="purchase_order", resource_id=po_id,
                     after={"invoiceId": invoice_id}, source="api", created_by=actor.sub)
        return True
    return False


@router.get("/purchase-orders")
def list_pos(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
             limit: int = Query(default=25, ge=1, le=100), cursor: str = Query(default=""), status_: str = Query(default="", alias="status"),
             supplier_id: str = Query(default="", alias="supplierId")) -> dict:
    stmt = select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id)
    if status_:
        stmt = stmt.where(PurchaseOrder.status == status_)
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    if cursor:
        cur = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(PurchaseOrder.created_at < cur.created_at,
                              ((PurchaseOrder.created_at == cur.created_at) & (PurchaseOrder.id < cursor))))
    stmt = stmt.order_by(desc(PurchaseOrder.created_at), desc(PurchaseOrder.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more, rows = len(rows) > limit, rows[:limit]
    names = supplier_names(db, actor.tenant_id, {p.supplier_id for p in rows})
    data = [{"id": p.id, "code": p.code, "status": p.status, "totalMinor": p.total_minor,
             "supplierId": p.supplier_id, "supplierName": names.get(p.supplier_id, "")} for p in rows]
    return envelope(data, {"limit": limit, "nextCursor": rows[-1].id if has_more and rows else "", "hasMore": has_more}, getattr(request.state, "request_id", ""))


@router.get("/purchase-orders/{pid}")
def get_po(pid: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == pid)).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    lines = list(db.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.tenant_id == actor.tenant_id, PurchaseOrderLine.po_id == pid).order_by(PurchaseOrderLine.line_no)).scalars())
    invs = list(db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.po_id == pid)).scalars())
    names = supplier_names(db, actor.tenant_id, {po.supplier_id})
    return envelope({"id": po.id, "code": po.code, "status": po.status, "totalMinor": po.total_minor,
                     "supplierId": po.supplier_id, "supplierName": names.get(po.supplier_id, ""), "currency": po.currency,
                     "lines": [{"id": l.id, "lineNo": l.line_no, "description": l.description, "quantity": l.quantity,
                                "unitPriceMinor": l.unit_price_minor, "lineTotalMinor": l.line_total_minor} for l in lines],
                     "invoices": [{"id": i.id, "code": i.code, "status": i.status} for i in invs]},
                    None, getattr(request.state, "request_id", ""))


@router.get("/invoices")
def list_invoices(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
                  limit: int = Query(default=25, ge=1, le=100), cursor: str = Query(default=""),
                  status_: str = Query(default="", alias="status"), po_id: str = Query(default="", alias="poId"),
                  supplier_id: str = Query(default="", alias="supplierId")) -> dict:
    """Invoice index. VNT-UI: there was no way to list or open an invoice at all —
    the only read path was nested three deep under `GET /purchase-orders/{id}`,
    which is why neither a dedicated invoices screen nor a supplier's invoice
    history could exist. Same keyset pagination as every other list here."""
    stmt = select(Invoice).where(Invoice.tenant_id == actor.tenant_id)
    if status_:
        stmt = stmt.where(Invoice.status == status_)
    if po_id:
        stmt = stmt.where(Invoice.po_id == po_id)
    if supplier_id:
        stmt = stmt.where(Invoice.supplier_id == supplier_id)
    if cursor:
        cur = db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(Invoice.created_at < cur.created_at,
                              ((Invoice.created_at == cur.created_at) & (Invoice.id < cursor))))
    stmt = stmt.order_by(desc(Invoice.created_at), desc(Invoice.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more, rows = len(rows) > limit, rows[:limit]
    po_codes = {p.id: p.code for p in db.execute(select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id.in_({i.po_id for i in rows if i.po_id}))).scalars()}
    names = supplier_names(db, actor.tenant_id, {i.supplier_id for i in rows})
    data = [{"id": i.id, "code": i.code, "status": i.status, "totalMinor": i.total_minor, "currency": i.currency,
             "poId": i.po_id or "", "poCode": po_codes.get(i.po_id or "", ""),
             "supplierId": i.supplier_id, "supplierName": names.get(i.supplier_id, ""),
             "createdAt": i.created_at.isoformat() if i.created_at else ""} for i in rows]
    return envelope(data, {"limit": limit, "nextCursor": rows[-1].id if has_more and rows else "", "hasMore": has_more}, getattr(request.state, "request_id", ""))


@router.get("/invoices/{iid}")
def get_invoice(iid: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    inv = db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.id == iid)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    lines = list(db.execute(select(InvoiceLine).where(InvoiceLine.tenant_id == actor.tenant_id, InvoiceLine.invoice_id == iid)).scalars())
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == inv.po_id)).scalar_one_or_none() if inv.po_id else None
    names = supplier_names(db, actor.tenant_id, {inv.supplier_id})
    return envelope({"id": inv.id, "code": inv.code, "status": inv.status, "totalMinor": inv.total_minor, "currency": inv.currency,
                     "poId": inv.po_id or "", "poCode": po.code if po else "",
                     "supplierId": inv.supplier_id, "supplierName": names.get(inv.supplier_id, ""),
                     "lines": [{"id": l.id, "poLineId": l.po_line_id, "quantity": l.quantity,
                                "unitPriceMinor": l.unit_price_minor, "lineTotalMinor": l.line_total_minor} for l in lines],
                     "createdAt": inv.created_at.isoformat() if inv.created_at else ""},
                    None, getattr(request.state, "request_id", ""))
