"""Catalog + budgets API — guided buying with hard budget enforcement.

- Catalog items: tenant-unique codes, UOM + reference prices for prefill.
- Budgets: per (category, YYYY-MM) ceilings; PO approval runs the hard check
  (committed same-category POs this period + this PO ≤ ceiling), 422 otherwise.
"""
from __future__ import annotations

import re
from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.catalog import Budget, CatalogItem
from ..models.purchase import PurchaseOrder
from ..services.audit import record_event

router = APIRouter(tags=["catalog"])
WRITE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer", "Category Manager", "Finance Reviewer"}


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _write(actor: Actor) -> None:
    if not set(actor.roles or ()) & WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for catalog write")


class ItemIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=300)
    category_id: str = ""
    uom: str = "each"
    ref_price_minor: int = Field(default=0, ge=0)
    currency: str = ""


class BudgetIn(BaseModel):
    category_id: str = ""
    period: str = Field(min_length=7, max_length=7)  # YYYY-MM
    ceiling_minor: int = Field(gt=0)


def current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def check_budget(db: Session, *, tenant_id: str, category_id: str, this_total: int, currency: str = "") -> dict:
    """Hard budget check (currency-scoped, DB-aggregated). Raises 422 when over ceiling."""
    if not category_id:
        return {"checked": False}
    period = current_period()
    b = db.execute(select(Budget).where(Budget.tenant_id == tenant_id, Budget.category_id == category_id, Budget.period == period)).scalar_one_or_none()
    if b is None:
        return {"checked": False}
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise HTTPException(status_code=500, detail="Invalid budget period")
    start = datetime(int(period[:4]), int(period[5:7]), 1, tzinfo=timezone.utc)
    end = datetime(start.year + (start.month == 12), start.month % 12 + 1, 1, tzinfo=timezone.utc)
    committed = db.execute(select(func.sum(PurchaseOrder.total_minor)).where(
        PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.category_id == category_id,
        PurchaseOrder.status.in_(["approved", "sent", "received", "invoiced"]),
        PurchaseOrder.created_at >= start, PurchaseOrder.created_at < end,
        *([PurchaseOrder.currency == currency] if currency else []))).scalar() or 0
    if committed + this_total > b.ceiling_minor:
        raise HTTPException(status_code=422, detail={"code": "BUDGET_EXCEEDED",
            "message": f"Budget exceeded: committed {committed} + this {this_total} > ceiling {b.ceiling_minor} for {period}"})
    return {"checked": True, "committed": int(committed), "ceiling": b.ceiling_minor}


@router.get("/catalog/items")
def list_items(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
               limit: int = Query(default=25, ge=1, le=100), cursor: str = Query(default=""),
               search: str = Query(default=""), category_id: str = Query(default="")) -> dict:
    stmt = select(CatalogItem).where(CatalogItem.tenant_id == actor.tenant_id, CatalogItem.status == "active")
    if category_id:
        stmt = stmt.where(CatalogItem.category_id == category_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(CatalogItem.name.ilike(like), CatalogItem.code.ilike(like)))
    if cursor:
        cur = db.execute(select(CatalogItem).where(CatalogItem.tenant_id == actor.tenant_id, CatalogItem.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(CatalogItem.created_at < cur.created_at,
                              ((CatalogItem.created_at == cur.created_at) & (CatalogItem.id < cursor))))
    stmt = stmt.order_by(desc(CatalogItem.created_at), desc(CatalogItem.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more, rows = len(rows) > limit, rows[:limit]
    data = [{"id": r.id, "code": r.code, "name": r.name, "uom": r.uom, "refPriceMinor": r.ref_price_minor, "currency": r.currency} for r in rows]
    return envelope(data, {"limit": limit, "nextCursor": rows[-1].id if has_more and rows else "", "hasMore": has_more}, getattr(request.state, "request_id", ""))


@router.post("/catalog/items", status_code=201)
def create_item(payload: ItemIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    row = CatalogItem(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                      code=payload.code.strip().upper(), name=payload.name.strip(), category_id=payload.category_id.strip(),
                      uom=payload.uom.strip() or "each", ref_price_minor=payload.ref_price_minor,
                      currency=payload.currency.strip().upper(), status="active")
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Catalog code exists") from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CATALOG_ITEM_CREATED", resource="catalog",
                 resource_id=row.id, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(row)
    return envelope({"id": row.id}, None, getattr(request.state, "request_id", ""))


@router.post("/budgets", status_code=201)
def set_budget(payload: BudgetIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", payload.period):
        raise HTTPException(status_code=422, detail="period must be YYYY-MM")
    row = Budget(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                 category_id=payload.category_id.strip(), period=payload.period, ceiling_minor=payload.ceiling_minor)
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Budget already set for this category+period") from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="BUDGET_SET", resource="budget",
                 resource_id=row.id, after={"ceiling": payload.ceiling_minor}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(row)
    return envelope({"id": row.id}, None, getattr(request.state, "request_id", ""))
