"""Spend API — real aggregates for premium dashboards (no vanity metrics).

Single source of truth: the SpendTransaction/SavingsRecord ledger written
server-side on PO send (commitment), invoice approval (actual) and award
(savings). Empty ledger => explicit zeros, never synthetic numbers.
"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.pricecase import PriceCase
from ..models.purchase import PurchaseOrderLine
from ..models.spend import SavingsRecord, SpendTransaction
from ..services.price_intel import ANOMALY_BP, PriceIntelError, baseline_for, normalize_item, variance_bp
from ..services.should_cost import ShouldCostError, gap_vs_quote, model_total
from ..services.spend_intel import concentration as _concentration
from ..services.spend_intel import cube as _cube
from ..services.spend_intel import leakage as _leakage
from ..services.spend_intel import maverick as _maverick

router = APIRouter(tags=["spend"])


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


@router.get("/spend/summary")
def summary(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    comm_rows = list(db.execute(
        select(SpendTransaction.supplier_id, SpendTransaction.currency, func.sum(SpendTransaction.amount_minor), func.count(SpendTransaction.id))
        .where(SpendTransaction.tenant_id == actor.tenant_id, SpendTransaction.kind == "commitment")
        .group_by(SpendTransaction.supplier_id, SpendTransaction.currency)).all())
    actual_total = db.execute(
        select(func.sum(SpendTransaction.amount_minor)).where(
            SpendTransaction.tenant_id == actor.tenant_id, SpendTransaction.kind == "actual")).scalar() or 0
    saved_total = db.execute(
        select(func.sum(SavingsRecord.saved_minor)).where(SavingsRecord.tenant_id == actor.tenant_id)).scalar() or 0
    by_supplier = [{"supplierId": s, "currency": c, "poTotalMinor": int(t or 0), "poCount": int(n or 0)} for s, c, t, n in comm_rows]
    return envelope({"poTotalMinor": sum(r["poTotalMinor"] for r in by_supplier),
                     "invoicedTotalMinor": int(actual_total),
                     "savedMinor": int(saved_total),
                     "bySupplier": sorted(by_supplier, key=lambda r: -r["poTotalMinor"])}, None, getattr(request.state, "request_id", ""))


@router.get("/spend/intelligence")
def intelligence(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """07 Spend Intelligence: cube + leakage + maverick + concentration in one call."""
    cells = _cube(db, actor.tenant_id)
    leak = _leakage(db, actor.tenant_id)
    mav = _maverick(db, actor.tenant_id)
    return envelope({"cube": cells,
                     "leakage": leak, "leakageTotalMinor": sum(l["totalMinor"] for l in leak),
                     "maverick": mav, "maverickTotalMinor": sum(m["totalMinor"] for m in mav),
                     "concentration": _concentration(cells)}, None, getattr(request.state, "request_id", ""))


class ShouldCostIn(BaseModel):
    material_minor: int = Field(ge=0)
    labor_minor: int = Field(ge=0)
    overhead_bp: int = Field(ge=0, le=10000)
    logistics_minor: int = Field(ge=0)
    margin_bp: int = Field(ge=0, le=10000)
    quoted_minor: int | None = Field(default=None, ge=0)


@router.post("/spend/should-cost")
def should_cost(payload: ShouldCostIn, request: Request, actor: Actor = Depends(get_actor)) -> dict:
    """Deterministic should-cost rollup (+ optional quote gap). Pure math, no storage."""
    try:
        breakdown = model_total(material_minor=payload.material_minor, labor_minor=payload.labor_minor,
                                overhead_bp=payload.overhead_bp, logistics_minor=payload.logistics_minor,
                                margin_bp=payload.margin_bp)
        out: dict = {"breakdown": breakdown}
        if payload.quoted_minor is not None:
            out["gap"] = gap_vs_quote(should_minor=breakdown["should_minor"], quoted_minor=payload.quoted_minor)
    except ShouldCostError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    return envelope(out, None, getattr(request.state, "request_id", ""))


@router.post("/spend/price-evaluate/{po_id}", status_code=201)
def price_evaluate(po_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Evaluate every PO line against its like-for-like baseline; open anomaly
    cases at |variance| >= 10%. Lines without enough history are SKIPPED with
    reasons (never fake-flagged)."""
    from ..models.purchase import PurchaseOrder
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == po_id)).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    lines = list(db.execute(select(PurchaseOrderLine).where(
        PurchaseOrderLine.tenant_id == actor.tenant_id, PurchaseOrderLine.po_id == po_id)).scalars())
    opened: list[str] = []
    skipped: list[dict] = []
    for ln in lines:
        dup = db.execute(select(PriceCase).where(PriceCase.tenant_id == actor.tenant_id,
                                                 PriceCase.po_line_id == ln.id, PriceCase.status == "open")).scalar_one_or_none()
        if dup is not None:
            skipped.append({"line": ln.line_no, "reason": "PRICE_CASE_OPEN"})
            continue
        try:
            base = baseline_for(db, tenant_id=actor.tenant_id, item=ln.description, supplier_id=po.supplier_id, exclude_po_id=po_id)
        except PriceIntelError as exc:
            skipped.append({"line": ln.line_no, "reason": exc.code})
            continue
        var = variance_bp(baseline_minor=base["baseline_minor"], quoted_minor=ln.unit_price_minor)
        if abs(var) >= ANOMALY_BP:
            case = PriceCase(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, po_id=po_id,
                             po_line_id=ln.id, supplier_id=po.supplier_id, item=normalize_item(ln.description),
                             baseline_minor=base["baseline_minor"], quoted_minor=ln.unit_price_minor,
                             variance_bp=var, samples=base["samples"], status="open",
                             detail={"line_no": ln.line_no})
            db.add(case)
            db.flush()
            opened.append(case.id)
    from ..services.audit import record_event as _rec

    _rec(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PRICE_EVALUATED", resource="purchase_order",
         resource_id=po_id, after={"opened": len(opened), "skipped": len(skipped)}, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"opened": opened, "skipped": skipped}, None, getattr(request.state, "request_id", ""))


@router.get("/spend/price-cases")
def price_cases(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
                status_: str = Query(default="", alias="status")) -> dict:
    stmt = select(PriceCase).where(PriceCase.tenant_id == actor.tenant_id)
    if status_:
        stmt = stmt.where(PriceCase.status == status_)
    rows = list(db.execute(stmt.order_by(PriceCase.created_at.desc()).limit(100)).scalars())
    return envelope([{"id": r.id, "item": r.item, "baselineMinor": r.baseline_minor, "quotedMinor": r.quoted_minor,
                      "varianceBp": r.variance_bp, "samples": r.samples, "status": r.status} for r in rows],
                    {"count": len(rows)}, getattr(request.state, "request_id", ""))


class ResolveIn(BaseModel):
    status: str = "dismissed"  # handed_off | dismissed


@router.post("/spend/price-cases/{case_id}/resolve", status_code=200)
def resolve_case(case_id: str, payload: ResolveIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    from ..services.audit import record_event as _rec2

    row = db.execute(select(PriceCase).where(PriceCase.tenant_id == actor.tenant_id, PriceCase.id == case_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if row.status != "open":
        raise HTTPException(status_code=422, detail="Only open cases can be resolved")
    if payload.status not in {"handed_off", "dismissed"}:
        raise HTTPException(status_code=422, detail="status must be handed_off|dismissed")
    row.status, row.updated_by = payload.status, actor.sub
    _rec2(db, tenant_id=actor.tenant_id, actor=actor.sub, action="PRICE_CASE_RESOLVED", resource="price_case",
          resource_id=case_id, after={"decision": payload.status}, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": case_id, "status": payload.status}, None, getattr(request.state, "request_id", ""))
