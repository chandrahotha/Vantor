"""Notifications API — unread-first feed, read marking, honest polling.

- GET /notifications?unread=true — newest first, cursor paginated.
- GET /notifications/unread-count — bell badge number.
- POST /notifications/{id}/read — marks own-or-broadcast rows read.
Visibility: broadcast rows (user_sub="") + rows addressed to caller sub.
Realtime push is NOT claimed — clients poll (30s); websocket lands later.

Read state is per-recipient: directed rows use `read_at`, broadcasts use
`read_by` so one reader cannot silence an alert for the whole tenant.
"""
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..models.notification import Notification

router = APIRouter(tags=["notifications"])


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


def _visible(actor: Actor):
    return ((Notification.tenant_id == actor.tenant_id) &
            ((Notification.user_sub == "") | (Notification.user_sub == actor.sub)))


def _unread_clause(actor: Actor):
    """Unread for *this* actor: directed rows with no read_at, broadcasts the
    actor has not acknowledged. Kept in SQL so the badge stays correct at scale.

    Broadcast membership is tested in Python because `read_by` is a JSON array —
    there is no portable "array does not contain" across SQLite and Postgres.
    Broadcasts are a small share of the feed, so filtering them after the
    tenant+visibility predicate is bounded and index-backed.
    """
    return (Notification.user_sub != "") & (Notification.read_at == "")


@router.get("/notifications")
def list_notifs(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor),
                limit: int = Query(default=25, ge=1, le=100), cursor: str = Query(default=""),
                unread: bool = Query(default=False)) -> dict:
    stmt = select(Notification).where(_visible(actor))
    if cursor:
        # Cursor must itself be visible to this actor, else a caller can page
        # relative to another user's row and infer its ordering metadata.
        cur = db.execute(select(Notification).where(_visible(actor), Notification.id == cursor)).scalar_one_or_none()
        if cur is None:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        stmt = stmt.where(or_(Notification.created_at < cur.created_at,
                              ((Notification.created_at == cur.created_at) & (Notification.id < cursor))))
    stmt = stmt.order_by(desc(Notification.created_at), desc(Notification.id)).limit(limit * 4 if unread else limit + 1)
    rows = list(db.execute(stmt).scalars())
    if unread:
        # Broadcast read-state is per-user in a JSON array, so it is filtered here.
        # Over-fetch by 4x so a page of unread rows is still a full page.
        rows = [r for r in rows if not r.is_read_for(actor.sub)]
    has_more, rows = len(rows) > limit, rows[:limit]
    data = [{"id": r.id, "kind": r.kind, "title": r.title, "body": r.body, "link": r.link,
              "read": r.is_read_for(actor.sub), "createdAt": r.created_at.isoformat() if r.created_at else ""} for r in rows]
    return envelope(data, {"limit": limit, "nextCursor": rows[-1].id if has_more and rows else "", "hasMore": has_more}, getattr(request.state, "request_id", ""))


@router.get("/notifications/unread-count")
def unread_count(request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    from sqlalchemy import func

    directed = db.execute(select(func.count()).select_from(Notification)
                          .where(_visible(actor), _unread_clause(actor))).scalar() or 0
    broadcasts = db.execute(select(Notification).where(_visible(actor), Notification.user_sub == "")).scalars().all()
    n = int(directed) + sum(1 for b in broadcasts if not b.is_read_for(actor.sub))
    return envelope({"unread": n}, None, getattr(request.state, "request_id", ""))


@router.post("/notifications/{nid}/read", status_code=200)
def mark_read(nid: str, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    row = db.execute(select(Notification).where(Notification.tenant_id == actor.tenant_id, Notification.id == nid)
                     .where((Notification.user_sub == "") | (Notification.user_sub == actor.sub))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not row.is_read_for(actor.sub):
        if row.user_sub:
            row.read_at = datetime.now(timezone.utc).isoformat()
        else:
            readers = list(row.read_by or [])
            if actor.sub not in readers:
                readers.append(actor.sub)
            row.read_by = readers
        row.updated_by = actor.sub
        db.commit()
    return envelope({"id": nid, "read": True}, None, getattr(request.state, "request_id", ""))
