"""Audit + idempotency models. Canonical writer lives in services/audit.py."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class AuditEvent(Base, TenantMixin):
    """Immutable, hash-chained audit row (SupplierRadar canonical pattern).

    hash = sha256(prev_hash + canonical_json(all fields except hash)).
    prev_hash = '' for the first event of a tenant (genesis).
    """

    __tablename__ = "audit_events"

    actor: Mapped[str] = mapped_column(String(256), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    before: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    after: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    approval: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="api", nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_audit_tenant_time", "tenant_id", "occurred_at"),
        Index("ix_audit_tenant_action", "tenant_id", "action"),
    )


class IdempotencyKey(Base, TenantMixin):
    """Stored responses for mutating requests carrying an Idempotency-Key header.

    `key` holds the *composed* fingerprint `method|path|header|sha256(body)`,
    not the raw header, so it is bounded by the longest path rather than by the
    header. 512 leaves room for a 512-char path plus a 128-char key plus the
    digest — see migration 0016.
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(512), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    status_code: Mapped[int] = mapped_column(nullable=False, default=200)
    response_body: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "key", "method", "path", name="uq_idem_tenant_key"),)
