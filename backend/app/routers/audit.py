"""Audit read API — tenant-scoped, auth-required. Writes happen server-side only.

- GET /api/v1/audit-events: cursor-paginated, newest first, actor/action/resource filters.
- GET /api/v1/audit-events/verify: recompute hash chain, report tamper status.
"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.audit import AuditEvent
from ..services.audit import verify_chain

router = APIRouter(tags=["audit"])


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


@router.get("/audit-events")
def list_events(
    request: Request,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(db_for_actor),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str = Query(default=""),
    action: str = Query(default=""),
    resource: str = Query(default=""),
) -> dict:
    stmt = select(AuditEvent).where(AuditEvent.tenant_id == actor.tenant_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if resource:
        stmt = stmt.where(AuditEvent.resource == resource)
    if cursor:
        # Keyset on (occurred_at, id) newest-first.
        cur = db.execute(select(AuditEvent).where(AuditEvent.tenant_id == actor.tenant_id, AuditEvent.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(AuditEvent.occurred_at < cur.occurred_at,
                              ((AuditEvent.occurred_at == cur.occurred_at) & (AuditEvent.id < cursor))))
    stmt = stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = rows[-1].id if has_more and rows else ""
    data = [
        {
            "id": r.id,
            "actor": r.actor,
            "action": r.action,
            "resource": r.resource,
            "resourceId": r.resource_id,
            "occurredAt": r.occurred_at.isoformat(),
            "reason": r.reason,
            "source": r.source,
            "hash": r.hash,
            "prevHash": r.prev_hash,
        }
        for r in rows
    ]
    rid = getattr(request.state, "request_id", "")
    return envelope(data, {"limit": limit, "nextCursor": next_cursor, "hasMore": has_more}, rid)


@router.get("/audit-events/verify")
def verify(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    ok, message, truncated = verify_chain(db, tenant_id=actor.tenant_id)
    rid = getattr(request.state, "request_id", "")
    return envelope({"valid": ok and not truncated, "message": message, "truncated": truncated}, None, rid)
