"""Integration models — Phase 8 Wave 1 (adapters + webhooks, no hard-coded providers).

Integration: a named adapter config (type + settings JSON, secrets NEVER stored
here — only a vault reference). WebhookEndpoint: tenant-owned HTTPS receivers
with per-endpoint HMAC secret reference; WebhookDelivery: each attempt with
status/latency (retry accounting for the worker).
"""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin

INTEGRATION_TYPES = {"erp", "finance", "email", "storage", "idp", "notify"}
DELIVERY_STATUSES = {"queued", "delivered", "failed"}


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

    endpoint_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (Index("ix_delivery_tenant_endpoint", "tenant_id", "endpoint_id"),)
