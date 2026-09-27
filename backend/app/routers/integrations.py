"""Integration API — adapters + webhook endpoints/deliveries.

- GET /integrations/types: adapter contract list (no provider hard-coded in core).
- POST /integrations: register a named adapter config (type must be known;
  secrets go to the vault — only `secret_ref: env:NAME` accepted).
- POST /webhooks/endpoints: register HTTPS receiver + event filter. The URL is
  put through `services.egress` before it is stored, not when it is first dialled.
- GET /webhooks/deliveries: premium-grid delivery log with status.
- POST /webhooks/deliveries/{id}/replay: return a dead letter to the queue.
- POST /webhooks/test {endpoint_id}: one synchronous signed ping, same retry
  accounting as the queue so it cannot report success the queue would not.
"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.integration import DELIVERY_STATUSES, INTEGRATION_TYPES, Integration, WebhookDelivery, WebhookEndpoint
from ..services.audit import record_event
from ..services.egress import EgressError, validate_url
from ..services.integration import ADAPTERS, deliver_now, drain, fanout, replay

router = APIRouter(tags=["integrations"])
WRITE_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer"}
#: Replaying or draining is an operator action, not a tenant action: it re-sends
#: a payload that has already been signed once, to a receiver the tenant chose.
OPERATIONS_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager"}


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _write(actor: Actor) -> None:
    if not set(actor.roles or ()) & WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for integration write")


def _operations(actor: Actor) -> None:
    if not set(actor.roles or ()) & OPERATIONS_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Insufficient role for delivery-queue operations")


class IntegrationIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    itype: str = Field(min_length=2, max_length=32)
    settings: dict = Field(default_factory=dict)
    secret_ref: str = ""


class EndpointIn(BaseModel):
    url: str = Field(min_length=9, max_length=1024)
    events: list[str] = Field(default_factory=list)
    secret_ref: str = ""


@router.get("/integrations/types")
def types(request: Request, actor: Actor = Depends(get_actor)) -> dict:
    return envelope({"adapters": sorted(ADAPTERS.keys()), "types": sorted(INTEGRATION_TYPES)}, None, getattr(request.state, "request_id", ""))


@router.post("/integrations", status_code=201)
def register(payload: IntegrationIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    _write(actor)
    if payload.itype not in INTEGRATION_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown integration type (one of {sorted(INTEGRATION_TYPES)})")
    if payload.secret_ref and not payload.secret_ref.startswith("env:"):
        raise HTTPException(status_code=422, detail="secret_ref must be a vault reference like env:NAME (never a raw secret)")
    row = Integration(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub, name=payload.name.strip(),
                      itype=payload.itype, status="disabled", settings=payload.settings, secret_ref=payload.secret_ref)
    db.add(row)
    db.flush()
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="INTEGRATION_REGISTERED", resource="integration",
                 resource_id=row.id, after={"type": payload.itype}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(row)
    return envelope({"id": row.id}, None, getattr(request.state, "request_id", ""))


@router.post("/webhooks/endpoints", status_code=201)
def add_endpoint(payload: EndpointIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Register a webhook receiver.

    VNT-007. The URL is validated *here*, at the point a tenant supplies it,
    rather than being stored and discovered to be a cloud-metadata address on the
    first delivery. `resolve=False` for the syntactic checks and a real
    resolution for the address policy: a URL that will not resolve is refused
    now, while the operator can still fix DNS, instead of producing a permanent
    `dead` row per event.
    """
    _write(actor)
    try:
        target = validate_url(payload.url)
    except EgressError as exc:
        raise HTTPException(status_code=422, detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.detail,
        }) from exc
    if payload.secret_ref and not payload.secret_ref.startswith("env:"):
        raise HTTPException(status_code=422, detail="secret_ref must be env:NAME")
    ep = WebhookEndpoint(tenant_id=actor.tenant_id, created_by=actor.sub, updated_by=actor.sub,
                         url=target.url, events=payload.events, status="active", secret_ref=payload.secret_ref)
    db.add(ep)
    db.flush()
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="WEBHOOK_REGISTERED", resource="webhook",
                 resource_id=ep.id, after={"url": target.url, "host": target.host}, source="api", created_by=actor.sub)
    db.commit()
    db.refresh(ep)
    return envelope({"id": ep.id, "host": target.host}, None, getattr(request.state, "request_id", ""))


@router.get("/webhooks/deliveries")
def deliveries(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
               limit: int = Query(default=25, ge=1, le=100), cursor: str = Query(default=""),
               status_: str = Query(default="", alias="status")) -> dict:
    stmt = select(WebhookDelivery).where(WebhookDelivery.tenant_id == actor.tenant_id)
    if status_:
        if status_ not in DELIVERY_STATUSES:
            raise HTTPException(status_code=422, detail={"code": "INVALID_STATUS",
                                                         "message": f"status must be one of {sorted(DELIVERY_STATUSES)}"})
        stmt = stmt.where(WebhookDelivery.status == status_)
    if cursor:
        cur = db.execute(select(WebhookDelivery).where(WebhookDelivery.tenant_id == actor.tenant_id, WebhookDelivery.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(WebhookDelivery.created_at < cur.created_at,
                              ((WebhookDelivery.created_at == cur.created_at) & (WebhookDelivery.id < cursor))))
    stmt = stmt.order_by(desc(WebhookDelivery.created_at), desc(WebhookDelivery.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more, rows = len(rows) > limit, rows[:limit]
    data = [{"id": d.id, "event": d.event, "status": d.status, "attempts": d.attempts,
             "lastError": d.last_error or "",
             "nextAttemptAt": d.next_attempt_at.isoformat() if d.next_attempt_at else None}
            for d in rows]
    return envelope(data, {"limit": limit, "nextCursor": rows[-1].id if has_more and rows else "", "hasMore": has_more}, getattr(request.state, "request_id", ""))


@router.post("/webhooks/deliveries/{did}/replay", status_code=200)
def replay_delivery(did: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Return a dead-lettered delivery to the queue."""
    _operations(actor)
    result = replay(db, tenant_id=actor.tenant_id, delivery_id=did)
    if result["status"] == "failed":
        raise HTTPException(status_code=409, detail={"code": "REPLAY_REFUSED", "message": result["error"]})
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="WEBHOOK_REPLAYED",
                 resource="webhook_delivery", resource_id=did, after=result, source="api", created_by=actor.sub)
    db.commit()
    return envelope(result, None, getattr(request.state, "request_id", ""))


@router.post("/webhooks/drain", status_code=200)
def drain_queue(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
                limit: int = Query(default=50, ge=1, le=200)) -> dict:
    """Attempt due deliveries now. The worker calls this on a schedule; an
    operator can call it after fixing a receiver, without waiting for the tick."""
    _operations(actor)
    results = drain(db, tenant_id=actor.tenant_id, limit=limit)
    return envelope({"results": results}, None, getattr(request.state, "request_id", ""))


class TestIn(BaseModel):
    endpoint_id: str = Field(min_length=1)


@router.post("/webhooks/test")
def test_ping(payload: TestIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """Deliver one signed ping synchronously so a tenant can verify their receiver.

    The body is the same shape the queue signs, and the retry accounting is the
    same, so a green ping means the queue will also deliver.
    """
    _write(actor)
    out = deliver_now(db, tenant_id=actor.tenant_id, endpoint_id=payload.endpoint_id,
                      event="ping", payload={"hello": "vantor"})
    return envelope({"delivery": out}, None, getattr(request.state, "request_id", ""))
