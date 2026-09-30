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
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
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
    #
    # The tail is selected by `(occurred_at, id)` because that pair is indexed
    # (`ix_audit_tenant_time`) and a chain append happens on every mutation in
    # the product, so this query has to stay cheap. That only identifies the
    # real tail if the ordering is a *total* order, which is what the
    # monotonic bump below guarantees.
    stmt = (
        select(AuditEvent.occurred_at, AuditEvent.hash)
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
    tail = db.execute(stmt).first()
    last_at: datetime | None = tail[0] if tail else None
    last_hash: str = (tail[1] if tail else "") or ""

    # `occurred_at` is strictly increasing within a tenant.
    #
    # Without this it is simply `datetime.now()`, which collides: two events
    # written in the same microsecond share a timestamp, and the only remaining
    # tiebreaker is `id` — a `uuid4().hex`, i.e. random. The writer then takes
    # the tail by `id DESC` while `verify_chain` walked by `id ASC`, so the row
    # the chain was appended to was not the row the verification visited, and a
    # tenant that had done nothing but ordinary work was told its tamper-evident
    # audit trail was broken. Eight such collisions occurred in a single pass of
    # `test_e2e_workflow`, which is why that test failed on a clean checkout.
    #
    # Nudging by a microsecond rather than introducing a sequence column keeps
    # the existing index useful and makes `(tenant_id, occurred_at)` unique in
    # practice. The drift from wall-clock time is bounded by the burst length in
    # microseconds, which is far below the resolution any audit consumer reads.
    occurred_at = datetime.now(timezone.utc)
    if last_at is not None:
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        if occurred_at <= last_at:
            occurred_at = last_at + timedelta(microseconds=1)
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
    """Returns (valid, message, truncated). Truncated=True means only a prefix was checked.

    The walk follows the chain's own links rather than re-sorting the rows by
    `(occurred_at, id)`.

    That sort was the bug. `id` is a random `uuid4().hex`, so for any two rows
    sharing a timestamp the ascending order the verification used and the
    descending order `record_event` used to find the tail disagreed about half
    the time — and the verification then reported a perfectly intact chain as
    broken. `record_event` no longer produces ties, but rows already written
    have them, so the ordering cannot be trusted as the source of truth for data
    that already exists.

    Following `prev_hash -> hash` is also what the tamper-evidence claim
    actually means. It proves the rows form one unbroken list from genesis, and
    it catches three things the sorted walk could not:

      * a fork - two rows appended to the same parent, which is what a lost
        `FOR UPDATE` under concurrency produces;
      * an orphan - a row whose parent is absent, i.e. a deletion from the
        middle of the chain;
      * more than one genesis row.
    """
    rows: list[AuditEvent] = list(
        db.execute(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)).scalars()
    )
    total = len(rows)
    if total == 0:
        return True, "verified 0 events", False

    by_parent: dict[str, list[AuditEvent]] = {}
    for row in rows:
        by_parent.setdefault(row.prev_hash or "", []).append(row)

    genesis = by_parent.get("", [])
    if len(genesis) != 1:
        return False, f"expected exactly one genesis event, found {len(genesis)}", False

    seen = 0
    prev = ""
    node: AuditEvent | None = genesis[0]
    while node is not None and seen < limit:
        payload = _payload_for(
            tenant_id=node.tenant_id,
            actor=node.actor,
            action=node.action,
            resource=node.resource,
            resource_id=node.resource_id,
            occurred_at=node.occurred_at,
            ip=node.ip,
            before=node.before,
            after=node.after,
            reason=node.reason,
            approval=node.approval,
            source=node.source,
        )
        if node.hash != compute_hash(prev, payload):
            return False, f"hash mismatch at {node.id}", False
        prev = node.hash
        seen += 1
        children = by_parent.get(node.hash, [])
        if len(children) > 1:
            return False, f"chain forks at {node.id} into {len(children)} successors", False
        node = children[0] if children else None

    if seen < limit and seen != total:
        return False, f"verified {seen} of {total} events — {total - seen} are not linked to the chain", False
    if seen >= limit and seen < total:
        return True, f"verified {seen} of {total} events (truncated at limit)", True
    return True, f"verified {seen} events", False
