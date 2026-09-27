"""Integration models — Phase 8 Wave 1 (adapters + webhooks, no hard-coded providers).

Integration: a named adapter config (type + settings JSON, secrets NEVER stored
here — only a vault reference). WebhookEndpoint: tenant-owned HTTPS receivers
with per-endpoint HMAC secret reference; WebhookDelivery: each attempt with
status/latency (retry accounting for the worker).

VNT-008. `DELIVERY_STATUSES` was `{queued, delivered, failed}` and the code
wrote `deferred` anyway — a status the log's own `?status=` filter rejected with
a 422, so deferred rows were unreachable through the API that reported them. The
set is now the complete state machine and the DB enforces it, so a fifth status
cannot be invented again without a schema change.

`pending` is the durable outbox state (enqueued, awaiting or retrying an
attempt), `delivered` is terminal success, and `dead` is the dead letter —
exhausted, or a permanent refusal such as a blocked egress destination. `dead`
is replayable via `POST /webhooks/deliveries/{id}/replay`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin

INTEGRATION_TYPES = {"erp", "finance", "email", "storage", "idp", "notify"}
DELIVERY_STATUSES = {"pending", "delivered", "failed", "dead"}
TERMINAL_DELIVERY_STATUSES = {"delivered", "dead"}


class Integration(Base, TenantMixin):
    __tablename__ = "integrations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    itype: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="disabled", nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(256), default="", nullable=False)

    __table_args__ = (Index("ix_integration_tenant_type", "tenant_id", "itype"),)


class WebhookEndpoint(Base, TenantMixin):
    __tablename__ = "webhook_endpoints"

    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    events: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(256), default="", nullable=False)

    __table_args__ = (Index("ix_hook_tenant_url", "tenant_id", "url"),)


class WebhookDelivery(Base, TenantMixin):
    __tablename__ = "webhook_deliveries"

    endpoint_id: Mapped[str] = mapped_column(String(36), ForeignKey("webhook_endpoints.id", ondelete="RESTRICT"), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # The exact bytes that were signed. Kept so a retry re-signs an identical
    # payload — re-serialising at delivery time would produce a different
    # signature for the same logical event and the receiver could not verify it.
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # When this row becomes eligible for another attempt. NULL means "now" for a
    # fresh row; a value means the backoff has not elapsed yet. The worker's
    # drain query is indexed on (status, next_attempt_at) for exactly this.
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_delivery_tenant_endpoint", "tenant_id", "endpoint_id"),
        Index("ix_delivery_due", "status", "next_attempt_at"),
        CheckConstraint(
            "status in ('pending','delivered','failed','dead')", name="ck_delivery_status"),
        CheckConstraint("attempts >= 0", name="ck_delivery_attempts_nonneg"),
    )
