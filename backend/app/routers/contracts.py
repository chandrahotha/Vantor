"""Contract API — repository + obligations + expiry roll (dashboard attention feed).

- Contracts: premium-grid list (search/status/supplier), create with real date
  validation, lifecycle PATCH, GET with obligations.
- Obligations: POST/GET per contract, status guards.
- POST /contracts/roll-expiry: server moves active→expiring where end_date
  within 90 days; returns moved ids. Powers "contracts expiring" dashboard
  cards and renewal alerts — computed, never seeded.
- Audit: CONTRACT_CREATED/STATUS_CHANGED, OBLIGATION_ADDED.
"""
from __future__ import annotations

from collections.abc import Generator
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.contract import Contract, ContractObligation
from ..models.catalog import ContractSignature
from ..models.matchrun import MatchRun
from ..models.purchase import Invoice, InvoiceLine, PurchaseOrder, PurchaseOrderLine
from ..models.supplier import Supplier
from ..services.audit import record_event
from ..services.contract import ContractError, check_dates, check_obligation, check_transition, is_due_expiring

router = APIRouter(tags=["contracts"])
WRITE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer", "Legal Reviewer", "Supplier Manager"}


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _write(actor: Actor) -> None:
    # Fail-closed: empty/missing roles can never write.
    if not set(actor.roles or ()) & WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for contract write")


class ContractIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    title: str = Field(min_length=2, max_length=300)
    supplier_id: str = ""
    contract_type: str = "supply"
    currency: str = ""
    value_minor: int = Field(default=0, ge=0)
    start_date: str = ""
    end_date: str = ""
    notes: str = ""


class ContractStatusIn(BaseModel):
    status: str


class ObligationIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    status: str = "open"
    due_date: str = ""
    owner: str = ""


def _dto(c: Contract, noblig: int = 0) -> dict:
    return {"id": c.id, "code": c.code, "title": c.title, "supplierId": c.supplier_id, "status": c.status,
            "contractType": c.contract_type, "currency": c.currency, "valueMinor": c.value_minor,
            "startDate": c.start_date, "endDate": c.end_date, "obligationCount": noblig,
            "createdAt": c.created_at.isoformat() if c.created_at else ""}


@router.get("/contracts")
def list_contracts(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
                   limit: int = Query(default=25, ge=1, le=100), cursor: str = Query(default=""),
                   sort: str = Query(default="created_at"), order: str = Query(default="desc"),
                   search: str = Query(default=""), status_: str = Query(default="", alias="status"),
                   expiring: bool = Query(default=False)) -> dict:
    if sort not in {"created_at", "code", "title", "status", "end_date"}:
        raise HTTPException(status_code=422, detail="Invalid sort")
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid order")
    col = {"created_at": Contract.created_at, "code": Contract.code, "title": Contract.title, "status": Contract.status, "end_date": Contract.end_date}[sort]
    stmt = select(Contract).where(Contract.tenant_id == actor.tenant_id)
    if status_:
        stmt = stmt.where(Contract.status == status_)
    if expiring:
        stmt = stmt.where(Contract.status == "expiring")
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Contract.title.ilike(like), Contract.code.ilike(like)))
    if cursor:
        cur = db.execute(select(Contract).where(Contract.tenant_id == actor.tenant_id, Contract.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        cv = getattr(cur, sort)
        stmt = stmt.where(or_(col < cv, ((col == cv) & (Contract.id < cursor)))) if order == "desc" else stmt.where(or_(col > cv, ((col == cv) & (Contract.id > cursor))))
    stmt = stmt.order_by(asc(col) if order == "asc" else desc(col), asc(Contract.id) if order == "asc" else desc(Contract.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more, rows = len(rows) > limit, rows[:limit]
    return envelope([_dto(r) for r in rows], {"limit": limit, "nextCursor": rows[-1].id if has_more and rows else "", "hasMore": has_more}, getattr(request.state, "request_id", ""))


@router.post("/contracts", status_code=201)
def create_contract(payload: ContractIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    code = payload.code.strip().upper()
    if len(code) < 2:
        raise HTTPException(status_code=422, detail="Invalid contract code")
    try:
        check_dates(payload.start_date, payload.end_date)
    except ContractError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    if payload.supplier_id:
        sup = db.execute(select(Supplier).where(Supplier.tenant_id == actor.tenant_id, Supplier.id == payload.supplier_id)).scalar_one_or_none()
        if sup is None:
            raise HTTPException(status_code=422, detail="Unknown supplier for this tenant")
    c = Contract(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, code=code,
                 title=payload.title.strip(), supplier_id=payload.supplier_id, status="draft",
                 contract_type=payload.contract_type.strip() or "supply", currency=payload.currency.strip().upper(),
                 value_minor=payload.value_minor, start_date=payload.start_date.strip(), end_date=payload.end_date.strip(),
                 notes=payload.notes.strip())
    db.add(c)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Contract code already exists in this tenant") from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CONTRACT_CREATED", resource="contract",
                 resource_id=c.id, after={"code": code}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(c)
    return envelope(_dto(c), None, getattr(request.state, "request_id", ""))


@router.get("/contracts/{contract_id}")
def get_contract(contract_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    c = db.execute(select(Contract).where(Contract.tenant_id == actor.tenant_id, Contract.id == contract_id)).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    obligs = list(db.execute(select(ContractObligation).where(ContractObligation.tenant_id == actor.tenant_id, ContractObligation.contract_id == contract_id).order_by(ContractObligation.due_date)).scalars())
    dto = _dto(c, len(obligs))
    dto["obligations"] = [{"id": o.id, "title": o.title, "status": o.status, "dueDate": o.due_date, "owner": o.owner} for o in obligs]
    return envelope(dto, None, getattr(request.state, "request_id", ""))


@router.patch("/contracts/{contract_id}/status")
def move_contract(contract_id: str, payload: ContractStatusIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    c = db.execute(select(Contract).where(Contract.tenant_id == actor.tenant_id, Contract.id == contract_id)).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    try:
        check_transition(c.status, payload.status)
    except ContractError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    before = c.status
    c.status, c.updated_by = payload.status, actor.sub
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CONTRACT_STATUS_CHANGED", resource="contract",
                 resource_id=c.id, before={"status": before}, after={"status": c.status}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(c)
    return envelope(_dto(c), None, getattr(request.state, "request_id", ""))


@router.post("/contracts/{contract_id}/obligations", status_code=201)
def add_obligation(contract_id: str, payload: ObligationIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    c = db.execute(select(Contract).where(Contract.tenant_id == actor.tenant_id, Contract.id == contract_id)).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    try:
        check_obligation(payload.status, payload.due_date)
    except ContractError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    o = ContractObligation(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, contract_id=contract_id,
                           title=payload.title.strip(), status=payload.status, due_date=payload.due_date.strip(), owner=payload.owner.strip())
    db.add(o)
    db.flush()
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="OBLIGATION_ADDED", resource="contract",
                 resource_id=contract_id, after={"obligation": o.title}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(o)
    return envelope({"id": o.id}, None, getattr(request.state, "request_id", ""))


@router.post("/contracts/roll-expiry")
def roll_expiry(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    today = date.today()
    moved: list[str] = []
    for c in db.execute(select(Contract).where(Contract.tenant_id == actor.tenant_id, Contract.status == "active")).scalars():
        try:
            due = is_due_expiring(c.status, c.end_date, today)
        except ContractError:
            continue
        if due:
            c.status, c.updated_by = "expiring", actor.sub
            record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CONTRACT_EXPIRING", resource="contract",
                         resource_id=c.id, after={"end_date": c.end_date}, source="system", created_by=actor.sub)
            moved.append(c.id)
    if moved:
        from ..services.notify import notify as _notify

        _notify(db, tenant_id=actor.tenant_id, kind="CONTRACT_EXPIRING",
                title=f"{len(moved)} contract(s) expiring within 90 days", link="/contracts", created_by=actor.sub)
    db.commit()
    return envelope({"moved": moved, "count": len(moved)}, None, getattr(request.state, "request_id", ""))


class SignIn(BaseModel):
    method: str = "internal"  # internal | esign
    provider: str = ""
    envelope_id: str = ""


@router.post("/contracts/{contract_id}/sign", status_code=201)
def sign_contract(contract_id: str, payload: SignIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Sign-off record. Internal = authenticated click; esign = external provider
    envelope (provider + envelope_id required; delivery verified by the adapter)."""
    _write(actor)
    import hashlib
    import json as _json

    c = db.execute(select(Contract).where(Contract.tenant_id == actor.tenant_id, Contract.id == contract_id)).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    if c.status not in {"review", "active", "expiring"}:
        raise HTTPException(status_code=422, detail="Only review/active/expiring contracts can be signed")
    if payload.method not in {"internal", "esign"}:
        raise HTTPException(status_code=422, detail="method must be internal|esign")
    if payload.method == "esign" and not (payload.provider.strip() and payload.envelope_id.strip()):
        raise HTTPException(status_code=422, detail="esign requires provider + envelope_id")
    snapshot = _json.dumps({"code": c.code, "title": c.title, "value": c.value_minor, "currency": c.currency,
                            "start": c.start_date, "end": c.end_date, "status": c.status},
                           sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(snapshot.encode()).hexdigest()
    sig = ContractSignature(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, contract_id=contract_id,
                            signer=actor.sub, method=payload.method, provider=payload.provider.strip(),
                            envelope_id=payload.envelope_id.strip(), snapshot_hash=digest)
    db.add(sig)
    db.flush()
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CONTRACT_SIGNED", resource="contract",
                 resource_id=contract_id, after={"method": payload.method, "snapshot": digest}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(sig)
    return envelope({"id": sig.id, "snapshotHash": digest}, None, getattr(request.state, "request_id", ""))


class MatchIn(BaseModel):
    po_id: str = Field(min_length=1)
    invoice_id: str = Field(min_length=1)


@router.post("/contracts/{contract_id}/match", status_code=201)
def run_match(contract_id: str, payload: MatchIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Run the 11-dim deterministic match over server-side rows; store the run."""
    from ..services.matching import MatchError, evaluate

    _write(actor)
    c = db.execute(select(Contract).where(Contract.tenant_id == actor.tenant_id, Contract.id == contract_id)).scalar_one_or_none()
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == actor.tenant_id, PurchaseOrder.id == payload.po_id)).scalar_one_or_none()
    inv = db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.id == payload.invoice_id)).scalar_one_or_none()
    if c is None or po is None or inv is None:
        raise HTTPException(status_code=404, detail="Contract, PO or invoice not found in this tenant")
    if inv.po_id != po.id:
        raise HTTPException(status_code=422, detail="Invoice does not belong to this PO")
    po_lines = list(db.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.tenant_id == actor.tenant_id, PurchaseOrderLine.po_id == po.id).order_by(PurchaseOrderLine.line_no)).scalars())
    inv_lines = list(db.execute(select(InvoiceLine).where(InvoiceLine.tenant_id == actor.tenant_id, InvoiceLine.invoice_id == inv.id)).scalars())
    prior = db.execute(select(Invoice).where(Invoice.tenant_id == actor.tenant_id, Invoice.po_id == po.id, Invoice.id != inv.id)).scalars()
    prior_count = len(list(prior))
    try:
        result = evaluate(
            contract={"supplier_id": c.supplier_id, "currency": c.currency, "value_minor": c.value_minor, "start_date": c.start_date, "end_date": c.end_date},
            po={"supplier_id": po.supplier_id, "currency": po.currency,
                "lines": [{"unit_price_minor": l.unit_price_minor, "quantity": l.quantity, "line_total_minor": l.line_total_minor} for l in po_lines]},
            invoice={"supplier_id": inv.supplier_id, "currency": inv.currency,
                     "lines": [{"unit_price_minor": l.unit_price_minor, "quantity": l.quantity, "line_total_minor": l.line_total_minor} for l in inv_lines]},
            prior_invoice_count=prior_count)
    except MatchError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    run = MatchRun(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, contract_id=contract_id,
                   po_id=po.id, invoice_id=inv.id, overall=result["overall"], hold_amount_minor=result["hold_amount_minor"],
                   verdict_hash=result["hash"], cells=result["cells"])
    db.add(run)
    db.flush()
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CONTRACT_MATCHED", resource="contract",
                 resource_id=contract_id, after={"overall": result["overall"], "hash": result["hash"]}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(run)
    return envelope({"id": run.id, **{k: v for k, v in result.items() if k != "cells"}, "cells": result["cells"]}, None, getattr(request.state, "request_id", ""))
