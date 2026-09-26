"""Spend API — real aggregates for premium dashboards (no vanity metrics).

Single source of truth: the SpendTransaction/SavingsRecord ledger written
server-side on PO send (commitment), invoice approval (actual) and award
(savings). Empty ledger => explicit zeros, never synthetic numbers.
"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.pricecase import PriceCase
from ..models.purchase import PurchaseOrderLine
from ..models.spend import SavingsRecord, SpendTransaction
from ..services.price_intel import ANOMALY_BP, BaselineCache, PriceIntelError, baseline_for, normalize_item, variance_bp
from ..services.should_cost import ShouldCostError, gap_vs_quote, model_total
from ..services.spend_intel import concentration as _concentration
from ..services.spend_intel import cube as _cube
from ..services.spend_intel import leakage as _leakage
from ..services.spend_intel import maverick as _maverick

router = APIRouter(tags=["spend"])

#: Roles that may run a price evaluation. Evaluation *opens* anomaly cases, and a
#: buyer triggering one on a PO they raised is the intended workflow, so this is
#: the ordinary write-role set used by the rest of the product.
EVALUATE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin",
                  "Procurement Manager", "Buyer", "Category Manager", "Finance Reviewer"}

#: Roles that may *resolve* a case. Resolving **retires the control** that flagged
#: it, so it is narrower than opening one: a Buyer who raised a PO must not be
#: able to dismiss the price anomaly raised against it. This router previously had
#: no role set at all, so `POST /spend/price-cases/{id}/resolve` was reachable by
#: any authenticated member of the tenant, `Read Only` included.
RESOLVE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin",
                 "Procurement Manager", "Finance Reviewer", "Category Manager"}


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _require(actor: Actor, roles: set[str], what: str) -> None:
    # Fail-closed: empty/missing roles can never write.
    if not set(actor.roles or ()) & roles:
        raise HTTPException(status_code=403, detail={
            "code": "INSUFFICIENT_ROLE",
            "message": f"Insufficient role to {what}",
        })


@router.get("/spend/summary")
def summary(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Ledger aggregates.

    Money is never summed across currencies: `byCurrency` is the authoritative
    per-currency breakdown. `poTotalMinor` / `invoicedTotalMinor` remain for
    single-currency tenants and are accompanied by `currencyCount` so a caller
    can refuse to render a meaningless cross-currency total.
    """
    comm_rows = list(db.execute(
        select(SpendTransaction.supplier_id, SpendTransaction.currency, func.sum(SpendTransaction.amount_minor), func.count(SpendTransaction.id))
        .where(SpendTransaction.tenant_id == actor.tenant_id, SpendTransaction.kind == "commitment")
        .group_by(SpendTransaction.supplier_id, SpendTransaction.currency)).all())
    actual_rows = list(db.execute(
        select(SpendTransaction.currency, func.sum(SpendTransaction.amount_minor))
        .where(SpendTransaction.tenant_id == actor.tenant_id, SpendTransaction.kind == "actual")
        .group_by(SpendTransaction.currency)).all())
    saved_rows = list(db.execute(
        select(SavingsRecord.currency, func.sum(SavingsRecord.saved_minor))
        .where(SavingsRecord.tenant_id == actor.tenant_id)
        .group_by(SavingsRecord.currency)).all())

    by_supplier = [{"supplierId": s, "currency": c, "poTotalMinor": int(t or 0), "poCount": int(n or 0)} for s, c, t, n in comm_rows]

    def _totals(pairs):  # type: ignore[no-untyped-def]
        acc: dict[str, int] = {}
        for ccy, amount in pairs:
            acc[ccy] = acc.get(ccy, 0) + int(amount or 0)
        return dict(sorted(acc.items(), key=lambda kv: -kv[1]))

    by_currency = {
        "committed": _totals([(c, t) for _, c, t, _ in comm_rows]),
        "invoiced": _totals(actual_rows),
        "saved": _totals(saved_rows),
    }
    currencies = sorted({c for grp in by_currency.values() for c in grp})
    return envelope({
        # Only meaningful when there is exactly one currency in play.
        "poTotalMinor": sum(v for v in by_currency["committed"].values()),
        "invoicedTotalMinor": sum(v for v in by_currency["invoiced"].values()),
        "savedMinor": sum(v for v in by_currency["saved"].values()),
        "byCurrency": by_currency,
        "currencies": currencies,
        "currencyCount": len(currencies),
        "bySupplier": sorted(by_supplier, key=lambda r: -r["poTotalMinor"]),
    }, None, getattr(request.state, "request_id", ""))


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
    _require(actor, EVALUATE_ROLES, "run a price evaluation")
    from ..models.purchase import PurchaseOrder
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == po_id)).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="PO not found")
    lines = list(db.execute(select(PurchaseOrderLine).where(
        PurchaseOrderLine.tenant_id == actor.tenant_id, PurchaseOrderLine.po_id == po_id)).scalars())
    # One pass over the already-open cases instead of one query per line, and
    # `price_cases` has no unique constraint on (po_line_id, status) — so the
    # old `scalar_one_or_none()` raised MultipleResultsFound (a 500) the moment
    # two concurrent evaluations opened a case on the same line.
    open_lines = {pc.po_line_id for pc in db.execute(select(PriceCase).where(
        PriceCase.tenant_id == actor.tenant_id, PriceCase.status == "open",
        PriceCase.po_line_id.in_([l.id for l in lines]))).scalars()} if lines else set()
    # The baseline is built from the tenant's PO-line descriptions and approved
    # invoices; share one cache across every line instead of rebuilding it per line.
    cache = BaselineCache(db, actor.tenant_id)
    opened: list[str] = []
    skipped: list[dict] = []
    for ln in lines:
        if ln.id in open_lines:
            skipped.append({"line": ln.line_no, "reason": "PRICE_CASE_OPEN"})
            continue
        try:
            base = baseline_for(db, tenant_id=actor.tenant_id, item=ln.description, supplier_id=po.supplier_id,
                                exclude_po_id=po_id, cache=cache)
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
    if opened:
        from ..services.notify import notify as _notify

        _notify(db, tenant_id=actor.tenant_id, kind="PRICE_ANOMALY", title=f"{len(opened)} price anomaly(ies) on PO {po.code}",
                body="Lines beyond like-for-like baseline. Review in Spend.", link="/spend", created_by=actor.sub)
    db.commit()
    return envelope({"opened": opened, "skipped": skipped}, None, getattr(request.state, "request_id", ""))


@router.get("/spend/price-cases")
def price_cases(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
                status_: str = Query(default="", alias="status"),
                limit: int = Query(default=25, ge=1, le=100), cursor: str = Query(default="")) -> dict:
    """Price anomaly cases, keyset paginated like every other list endpoint.

    This one was hard-limited to 100 with no cursor and no stable ordering, so a
    tenant with more than 100 cases could see only the newest slice and had no
    way to reach anything older — the review queue silently truncated.
    """
    stmt = select(PriceCase).where(PriceCase.tenant_id == actor.tenant_id)
    if status_:
        stmt = stmt.where(PriceCase.status == status_)
    if cursor:
        cur = db.execute(select(PriceCase).where(PriceCase.tenant_id == actor.tenant_id, PriceCase.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(PriceCase.created_at < cur.created_at,
                              ((PriceCase.created_at == cur.created_at) & (PriceCase.id < cursor))))
    stmt = stmt.order_by(desc(PriceCase.created_at), desc(PriceCase.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more = len(rows) > limit
    rows = rows[:limit]
    data = [{"id": r.id, "poId": r.po_id, "supplierId": r.supplier_id, "item": r.item,
             "baselineMinor": r.baseline_minor, "quotedMinor": r.quoted_minor,
             "varianceBp": r.variance_bp, "samples": r.samples, "status": r.status,
             "createdAt": r.created_at.isoformat() if r.created_at else ""} for r in rows]
    return envelope(data, {"limit": limit, "nextCursor": data[-1]["id"] if has_more and data else "",
                           "hasMore": has_more, "count": len(data)}, getattr(request.state, "request_id", ""))


class ResolveIn(BaseModel):
    status: str = "dismissed"  # handed_off | dismissed


@router.post("/spend/price-cases/{case_id}/resolve", status_code=200)
def resolve_case(case_id: str, payload: ResolveIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    from ..services.audit import record_event as _rec2

    _require(actor, RESOLVE_ROLES, "resolve a price case")
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
