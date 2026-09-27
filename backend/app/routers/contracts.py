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

#: VNT-022. One flat seven-role write set guarded every action: drafting a
#: contract, moving it through the lifecycle, activating it, and signing it. A
#: `Buyer` could activate and sign, which is the opposite of the separation the
#: `Legal Reviewer` role exists to provide.
#:
#: Authority is now per action, and every route names which one it needs:
#:
#:   edit   — draft the terms. Commercial/procurement.
#:   review — send it into legal review, and move it out of review. Legal.
#:   activate/terminate/renew — make it binding. Legal plus procurement manager.
#:   sign   — sign on the organisation's behalf. Legal only, and never the drafter.
#:   expire — the server-derived expiry roll. A service identity, not a human.
ACTION_ROLES: dict[str, set[str]] = {
    "edit": {"Super Admin", "Organization Admin", "Procurement Admin",
             "Procurement Manager", "Buyer", "Legal Reviewer"},
    "review": {"Super Admin", "Organization Admin", "Procurement Admin",
               "Procurement Manager", "Legal Reviewer"},
    "activate": {"Super Admin", "Organization Admin", "Procurement Admin",
                 "Procurement Manager", "Legal Reviewer"},
    "terminate": {"Super Admin", "Organization Admin", "Procurement Admin", "Legal Reviewer"},
    "renew": {"Super Admin", "Organization Admin", "Procurement Admin",
              "Procurement Manager", "Legal Reviewer"},
    "sign": {"Super Admin", "Organization Admin", "Procurement Admin", "Legal Reviewer"},
    "obligation": {"Super Admin", "Organization Admin", "Procurement Admin",
                   "Procurement Manager", "Buyer", "Legal Reviewer"},
    # The expiry roll is derived from dates, not a judgement. It runs on a
    # schedule through a service identity; a tenant's procurement manager must not
    # be able to trigger a bulk status change with a click.
    "expire": {"Super Admin"},
}

#: The destination status decides which authority the transition needs.
TRANSITION_ACTION: dict[str, str] = {
    "review": "review",
    "active": "activate",
    "renewed": "renew",
    "expired": "expire",
    "terminated": "terminate",
    "expiring": "expire",
}


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _write(actor: Actor) -> None:
    # Fail-closed: empty/missing roles can never write.
    if not set(actor.roles or ()) & WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for contract write")


def _require(actor: Actor, action: str) -> None:
    """Authority for one named action. The single gate every contract write uses."""
    allowed = ACTION_ROLES[action]
    if not set(actor.roles or ()) & allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "code": "CONTRACT_ACTION_FORBIDDEN",
            "message": f"Role required for this contract action: {action}",
            "details": {"action": action, "allowedRoles": sorted(allowed)},
        })


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
    """Move a contract through its lifecycle.

    VNT-022: this used to be guarded by the same flat write set as drafting, so
    `Buyer` and `Supplier Manager` could take a contract to `active`. The
    authority is now derived from the *destination* status, so activating needs
    activation authority and moving into legal review needs legal authority.
    """
    c = db.execute(select(Contract).where(Contract.tenant_id == actor.tenant_id, Contract.id == contract_id).with_for_update()).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    _require(actor, TRANSITION_ACTION.get(payload.status, "edit"))
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
def roll_expiry(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
                as_of: str = Query(default="", description="ISO date to evaluate against; defaults to today")) -> dict:
    """Derive `expiring` from end dates. Idempotent, and clock-injectable.

    VNT-024. This used to call `date.today()` inline behind a broad write gate,
    so any of the seven write roles could trigger a bulk status change and the
    date logic was untestable without a freezegun. Both are fixed: authority is
    `expire` (a service identity, not a tenant click), and the date is a parameter
    so a test can move the clock.

    Idempotency is structural rather than incidental: the query only considers
    contracts that are currently `active`, so a second run moves nothing.
    """
    _require(actor, "expire")
    today = _parse_day(as_of) if as_of else _tenant_today(actor.tenant_id)
    moved: list[str] = []
    for c in db.execute(select(Contract).where(
            Contract.tenant_id == actor.tenant_id, Contract.status == "active").with_for_update()).scalars():
        try:
            due = is_due_expiring(c.status, c.end_date, today)
        except ContractError:
            continue
        if due:
            c.status, c.updated_by = "expiring", actor.sub
            record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CONTRACT_EXPIRING", resource="contract",
                         resource_id=c.id, after={"end_date": c.end_date, "as_of": today.isoformat()}, source="system", created_by=actor.sub)
            moved.append(c.id)
    if moved:
        from ..services.notify import notify as _notify

        _notify(db, tenant_id=actor.tenant_id, kind="CONTRACT_EXPIRING",
                title=f"{len(moved)} contract(s) expiring within 90 days", link="/contracts", created_by=actor.sub)
    db.commit()
    return envelope({"moved": moved, "count": len(moved), "asOf": today.isoformat()},
                    None, getattr(request.state, "request_id", ""))


def _parse_day(value: str):
    from datetime import date as _date

    try:
        return _date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "AS_OF_INVALID",
            "message": f"as_of must be an ISO date (YYYY-MM-DD), got {value!r}"}) from exc


def _tenant_today(tenant_id: str):
    """Today in the tenant's timezone, falling back to UTC.

    VNT-041: "within 90 days" is a business judgement made in the buyer's
    working day, not the server's. A tenant at UTC-12 reaches its own 1 January
    twelve hours before a UTC server does, which is exactly the kind of off-by-one
    that makes a renewal notice fire a day early or a day late.
    """
    from datetime import datetime, timedelta, timezone

    from ..core.config import get_settings

    tz_name = (get_settings().contract_timezone or "UTC").strip()
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        # An unknown zone must not stop the roll; UTC is the safe default and the
        # response reports the zone actually used.
        tz = timezone.utc
    return datetime.now(tz).date()


class SignIn(BaseModel):
    method: str = "internal"  # internal | esign
    provider: str = ""
    envelope_id: str = ""


@router.post("/contracts/{contract_id}/sign", status_code=201)
def sign_contract(contract_id: str, payload: SignIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Record a sign-off.

    VNT-022/023. Two defects, both fixed here.

    *Authority*: this was guarded by the flat write set, so a `Buyer` could sign.
    It now requires `sign` authority, and the drafter is excluded by
    segregation of duties — the person who wrote the terms does not get to bind
    them.

    *Verification*: an `esign` row used to be written as a completed signature
    from nothing more than a caller-supplied provider name and envelope id, and
    the response said 201. There was no column in which the provider's answer
    could even be recorded. An e-sign is now created `pending` and the contract
    is **not** treated as signed; it becomes signed only when the provider
    confirms, either by the inbound callback below or by `POST .../sign/verify`.
    """
    from datetime import datetime, timezone

    import hashlib
    import json as _json

    _require(actor, "sign")
    c = db.execute(select(Contract).where(Contract.tenant_id == actor.tenant_id, Contract.id == contract_id).with_for_update()).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    if c.status not in {"review", "active", "expiring"}:
        raise HTTPException(status_code=422, detail="Only review/active/expiring contracts can be signed")
    # Segregation of duties: the drafter does not sign.
    if c.created_by and c.created_by == actor.sub:
        raise HTTPException(status_code=403, detail={
            "code": "SIGNATURE_SOD",
            "message": "The author of a contract cannot sign it (segregation of duties)"})
    if payload.method not in {"internal", "esign"}:
        raise HTTPException(status_code=422, detail="method must be internal|esign")
    if payload.method == "esign" and not (payload.provider.strip() and payload.envelope_id.strip()):
        raise HTTPException(status_code=422, detail="esign requires provider + envelope_id")
    snapshot = _json.dumps({"code": c.code, "title": c.title, "value": c.value_minor, "currency": c.currency,
                            "start": c.start_date, "end": c.end_date, "status": c.status},
                           sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(snapshot.encode()).hexdigest()
    # An internal signature is an authenticated click and is complete on arrival.
    # An external one is a *claim* that someone else has to confirm.
    now = datetime.now(timezone.utc)
    sig = ContractSignature(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, contract_id=contract_id,
                            signer=actor.sub, method=payload.method, provider=payload.provider.strip(),
                            envelope_id=payload.envelope_id.strip(), snapshot_hash=digest,
                            status="signed" if payload.method == "internal" else "pending",
                            verified_at=now if payload.method == "internal" else None,
                            # An internal signature is an authenticated click, not a
                            # provider claim, and saying so is the difference
                            # between a truthful provenance column and a decorative
                            # one. An e-sign row starts with no provenance at all:
                            # it has not been verified by anyone yet.
                            verified_via="internal_click" if payload.method == "internal" else "")
    db.add(sig)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={
            "code": "ENVELOPE_ALREADY_OPEN",
            "message": "This provider envelope already has an open signature request"}) from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CONTRACT_SIGNED", resource="contract",
                 resource_id=contract_id, after={"method": payload.method, "snapshot": digest,
                                                 "signatureStatus": sig.status}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(sig)
    return envelope({
        "id": sig.id,
        "snapshotHash": digest,
        # `signed: false` for an e-sign is the honest answer. A client that only
        # checked for a 2xx used to believe these were complete.
        "signed": sig.status == "signed",
        "status": sig.status,
        "pendingVerification": sig.status == "pending",
    }, None, getattr(request.state, "request_id", ""))


class VerifySignIn(BaseModel):
    """The provider's own answer about an envelope."""
    envelope_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(default="", max_length=64)
    status: str = Field(min_length=1, max_length=16)  # signed | declined | voided | pending
    payload: dict = Field(default_factory=dict)


@router.post("/contracts/signatures/provider-callback", status_code=200)
async def provider_signature_callback(
    request: Request,
    provider: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
) -> dict:
    """An e-sign provider's answer, authenticated by HMAC.

    This is the path where the *provider* states that an envelope was signed, and
    the only one where the platform can honestly record a verified e-signature.
    `POST /contracts/{id}/sign/verify` is the same transition performed by a
    trusted human; both write a signature row, and `verified_via` records which
    one produced it.

    Unauthenticated by design — the caller is the provider, not a VANTOR user — so
    the request is authenticated by the MAC instead. Three consequences, all
    deliberate:

    * **No user session, so `get_actor` is not used.** Requiring one would mean
      the provider had to hold a VANTOR user's token, which is exactly the
      confusion this endpoint exists to avoid.
    * **Every refusal is the same shape.** An unknown envelope and a bad
      signature produce the same status and comparable wording, so the endpoint
      cannot be used to discover which envelope ids exist.
    * **It is rate limited like any other unauthenticated request.** The limiter
      counts traffic it cannot attribute against the peer address rather than
      skipping it, which is what makes an unauthenticated endpoint safe to
      expose at all.

    The provider's shared secret is read from the environment (`env:`-style
    reference only, never stored) and a provider with no secret configured is
    refused — "not configured" must never mean "verification skipped".
    """
    from ..services import esign

    provider = provider.strip()
    raw = await request.body()
    try:
        esign.verify_callback(
            provider=provider,
            timestamp=request.headers.get("X-ESign-Timestamp", ""),
            body=raw,
            signature=request.headers.get("X-ESign-Signature", ""),
        )
        payload = esign.parse_body(raw)
        sig, before = esign.apply_callback(
            db,
            provider=provider,
            envelope_id=str(payload.get("envelope_id") or ""),
            status=str(payload.get("status") or ""),
            payload=payload,
        )
    except esign.CallbackError as exc:
        db.rollback()
        # 401 means "we do not believe you are the provider"; 422 means "you are
        # the provider and your request is wrong". The split is safe precisely
        # because every 422 branch sits *after* the MAC has been verified, so an
        # attacker without the shared secret can never reach one and cannot use
        # the status code to tell an unknown envelope from a bad signature.
        # Collapsing them to one code would hide real provider misconfiguration
        # behind an authentication error it does not deserve.
        if exc.code in {
            "ESIGN_SIGNATURE_INVALID",
            "ESIGN_TIMESTAMP_STALE",
            "ESIGN_TIMESTAMP_INVALID",
            "ESIGN_PROVIDER_NOT_CONFIGURED",
        }:
            code, message = status.HTTP_401_UNAUTHORIZED, "Callback rejected"
        else:
            code, message = status.HTTP_422_UNPROCESSABLE_CONTENT, exc.message
        raise HTTPException(status_code=code, detail={
            "code": exc.code, "message": message}) from exc

    record_event(db, tenant_id=sig.tenant_id, actor=f"provider:{provider}",
                 action="CONTRACT_SIGNATURE_PROVIDER_CALLBACK", resource="contract",
                 resource_id=sig.contract_id,
                 before={"status": before},
                 after={"status": sig.status, "envelope": sig.envelope_id,
                        "verifiedVia": sig.verified_via},
                 source="provider_webhook", created_by=f"provider:{provider}")
    db.commit()
    return {"data": {"id": sig.id, "status": sig.status, "verifiedVia": sig.verified_via},
            "pagination": None}


@router.post("/contracts/{contract_id}/sign/verify", status_code=200)
def verify_signature(contract_id: str, payload: VerifySignIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Apply a provider's confirmation to an open e-signature.

    This is the **operator-attested** path, not the verified one. A legal
    reviewer with `sign` authority is asserting what the provider said; the
    platform is not checking with the provider at all. That is a legitimate and
    sometimes necessary thing to do — a provider can be unreachable, or a
    migration can leave envelopes whose confirmations were never delivered — but
    it is a different claim from "the provider confirmed this", and until
    VNT-023's second half it was recorded identically.

    So the row is stamped `verified_via = 'manual_reconciliation'`, the audit
    event says so, and `ck_signature_esign_verified_via` refuses a signed e-sign
    row with no provenance at all. A verified provider callback is the other
    route: `POST /contracts/signatures/provider-callback`.

    It is a first-class endpoint rather than an out-of-band adapter call because
    the provider's answer has to land on the right row, and the only thing that
    can identify that row reliably is the envelope id the tenant registered.
    """
    from datetime import datetime, timezone

    _require(actor, "sign")
    c = db.execute(select(Contract).where(Contract.tenant_id == actor.tenant_id, Contract.id == contract_id)).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    target = payload.status.strip().lower()
    if target not in {"signed", "declined", "voided", "pending"}:
        raise HTTPException(status_code=422, detail={
            "code": "SIGNATURE_STATUS_INVALID",
            "message": "status must be one of signed, declined, voided, pending"})
    stmt = select(ContractSignature).where(
        ContractSignature.tenant_id == actor.tenant_id,
        ContractSignature.contract_id == contract_id,
        ContractSignature.envelope_id == payload.envelope_id,
        # An internal signature has no envelope, so this also keeps internal rows
        # out of the match when `envelope_id` is empty.
        ContractSignature.envelope_id != "")
    if payload.provider.strip():
        stmt = stmt.where(ContractSignature.provider == payload.provider.strip())
    sig = db.execute(stmt.with_for_update()).scalar_one_or_none()
    if sig is None:
        raise HTTPException(status_code=404, detail={
            "code": "SIGNATURE_ENVELOPE_NOT_FOUND",
            "message": "No open signature for that envelope on this contract"})
    if sig.status in {"signed", "declined", "voided"} and target != sig.status:
        raise HTTPException(status_code=409, detail={
            "code": "SIGNATURE_ALREADY_TERMINAL",
            "message": f"This envelope is already {sig.status}",
            "details": {"status": sig.status}})
    before = sig.status
    sig.status = target
    sig.provider_payload = payload.payload or {}
    sig.verified_at = datetime.now(timezone.utc) if target == "signed" else sig.verified_at
    # The provenance of this claim. Without it a row confirmed by the provider's
    # signed callback and a row a reviewer typed are the same object in the
    # database, in the API and in the audit chain.
    sig.verified_via = "internal_click" if sig.method == "internal" else "manual_reconciliation"
    sig.updated_by = actor.sub
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="CONTRACT_SIGNATURE_VERIFIED",
                 resource="contract", resource_id=contract_id,
                 before={"status": before},
                 after={"status": target, "envelope": payload.envelope_id,
                        "verifiedVia": sig.verified_via},
                 source="api", created_by=actor.sub)
    db.commit()
    db.refresh(sig)
    return envelope({"id": sig.id, "status": sig.status, "signed": sig.status == "signed"},
                    None, getattr(request.state, "request_id", ""))


@router.get("/contracts/{contract_id}/signatures")
def list_signatures(contract_id: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Every signature on a contract, with its verification state."""
    rows = list(db.execute(select(ContractSignature).where(
        ContractSignature.tenant_id == actor.tenant_id,
        ContractSignature.contract_id == contract_id).order_by(ContractSignature.created_at)).scalars())
    return envelope([{
        "id": s.id, "signer": s.signer, "method": s.method, "status": s.status,
        "provider": s.provider, "envelopeId": s.envelope_id, "snapshotHash": s.snapshot_hash,
        "verifiedAt": s.verified_at.isoformat() if s.verified_at else None,
        "createdAt": s.created_at.isoformat() if s.created_at else "",
    } for s in rows], None, getattr(request.state, "request_id", ""))


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
    # Only the columns the duplicate check needs, from every OTHER invoice on this
    # PO. Counting invoices instead (the old behaviour) failed the second
    # invoice of any partially-paid PO, holding legitimate money for ever.
    prior_rows = db.execute(
        select(InvoiceLine.po_line_id, InvoiceLine.quantity, InvoiceLine.unit_price_minor)
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .where(InvoiceLine.tenant_id == actor.tenant_id, Invoice.po_id == po.id,
               Invoice.id != inv.id)).all()
    prior_lines = [{"po_line_id": r[0], "quantity": r[1], "unit_price_minor": r[2]} for r in prior_rows]
    try:
        result = evaluate(
            contract={"supplier_id": c.supplier_id, "currency": c.currency, "value_minor": c.value_minor, "start_date": c.start_date, "end_date": c.end_date},
            po={"supplier_id": po.supplier_id, "currency": po.currency,
                "lines": [{"po_line_id": l.id, "unit_price_minor": l.unit_price_minor, "quantity": l.quantity, "line_total_minor": l.line_total_minor} for l in po_lines]},
            invoice={"supplier_id": inv.supplier_id, "currency": inv.currency,
                     "lines": [{"po_line_id": l.po_line_id, "unit_price_minor": l.unit_price_minor, "quantity": l.quantity, "line_total_minor": l.line_total_minor} for l in inv_lines]},
            prior_invoice_lines=prior_lines,
            po_line_quantities={l.id: l.quantity for l in po_lines})
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
