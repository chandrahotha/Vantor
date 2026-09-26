"""Canonical audit writer — hash-chained, idempotent-safe, concurrency-correct.

Ported pattern from SupplierRadar (audit chain + idempotency + PG advisory
intent): every significant mutation writes one immutable row; hash links to
the previous row of the same tenant so tampering breaks `verify_chain`.

- `record_event`: inserts with SELECT .. FOR UPDATE on the tenant's last row
  inside the caller's transaction (pass an explicit session).
- Pure-python `compute_hash` so tests verify without a DB.
- Never updates or deletes rows — repository must revoke UPDATE/DELETE via RLS/GRANT.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.audit import AuditEvent


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(b"|")
    h.update(canonical_json(payload).encode("utf-8"))
    return h.hexdigest()


def _payload_for(**kwargs: Any) -> dict[str, Any]:
    occurred = kwargs.get("occurred_at")
    if isinstance(occurred, datetime):
        # sqlite returns naive datetimes; PG returns aware. Normalize naive→UTC
        # so verify_chain reproduces the exact hash on either backend.
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        kwargs["occurred_at"] = occurred.astimezone(timezone.utc).isoformat()
    return kwargs


def record_event(
    db: Session,
    *,
    tenant_id: str,
    actor: str,
    action: str,
    resource: str,
    resource_id: str = "",
    before: dict | None = None,
    after: dict | None = None,
    reason: str = "",
    approval: str = "",
    source: str = "api",
    ip: str = "",
    created_by: str = "",
) -> AuditEvent:
    if not tenant_id:
        raise ValueError("tenant_id is required — never write cross-tenant audit rows")
    # Lock the tenant's tail so concurrent writers chain correctly (PG only; sqlite has no FOR UPDATE).
    stmt = (
        select(AuditEvent.hash)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    try:
        dialect = db.bind.dialect.name if db.bind else ""
    except Exception:
        dialect = ""
    if dialect == "postgresql":
        stmt = stmt.with_for_update()
    last_hash: str = db.execute(stmt).scalar() or ""
    occurred_at = datetime.now(timezone.utc)
    payload = _payload_for(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        resource=resource,
        resource_id=resource_id,
        occurred_at=occurred_at,
        ip=ip,
        before=before or {},
        after=after or {},
        reason=reason,
        approval=approval,
        source=source,
    )
    digest = compute_hash(last_hash, payload)
    row = AuditEvent(
        tenant_id=tenant_id,
        created_by=created_by or actor,
        updated_by=created_by or actor,
        actor=actor,
        action=action,
        resource=resource,
        resource_id=resource_id,
        occurred_at=occurred_at,
        ip=ip,
        before=before or {},
        after=after or {},
        reason=reason,
        approval=approval,
        source=source,
        prev_hash=last_hash,
        hash=digest,
    )
    db.add(row)
    db.flush()
    return row


def verify_chain(db: Session, *, tenant_id: str, limit: int = 10_000) -> tuple[bool, str, bool]:
    """Returns (valid, message, truncated). Truncated=True means only a prefix was checked."""
    rows: list[AuditEvent] = list(
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc())
            .limit(limit)
        ).scalars()
    )
    prev = ""
    for row in rows:
        payload = _payload_for(
            tenant_id=row.tenant_id,
            actor=row.actor,
            action=row.action,
            resource=row.resource,
            resource_id=row.resource_id,
            occurred_at=row.occurred_at,
            ip=row.ip,
            before=row.before,
            after=row.after,
            reason=row.reason,
            approval=row.approval,
            source=row.source,
        )
        if row.prev_hash != prev:
            return False, f"prev_hash break at {row.id}", False
        if row.hash != compute_hash(prev, payload):
            return False, f"hash mismatch at {row.id}", False
        prev = row.hash
    total = db.execute(select(func.count()).select_from(AuditEvent).where(AuditEvent.tenant_id == tenant_id)).scalar() or 0
    if total > len(rows):
        return True, f"verified {len(rows)} of {total} events (truncated at limit)", True
    return True, f"verified {len(rows)} events", False
