"""Notifications — tenant + user scoped feed (RUN 2).

Emitted server-side by domain events (award decided, approval decided, invoice
approved, contract expiring, price anomaly opened, qualification decided).
Delivery is honest polling (bell polls /notifications/unread-count every 30s);
realtime push (websocket) is a documented later step, never faked here.
"""
from __future__ import annotations

from sqlalchemy import Index, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class Notification(Base, TenantMixin):
    __tablename__ = "notifications"

    user_sub: Mapped[str] = mapped_column(String(256), default="", nullable=False)  # "" = whole-tenant broadcast
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    link: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    read_at: Mapped[str] = mapped_column(String(32), default="", nullable=False)  # ISO or "" = unread

    __table_args__ = (Index("ix_notif_tenant_user", "tenant_id", "user_sub"),)
