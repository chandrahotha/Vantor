"""Notify helper — single choke point for all server-side notifications."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.notification import Notification


def notify(db: Session, *, tenant_id: str, kind: str, title: str, body: str = "",
           link: str = "", user_sub: str = "", created_by: str = "") -> Notification:
    row = Notification(tenant_id=tenant_id, created_by=created_by or "system", updated_by=created_by or "system",
                       user_sub=user_sub, kind=kind, title=title, body=body, link=link)
    db.add(row)
    db.flush()
    return row
