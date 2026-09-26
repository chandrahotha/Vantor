"""Notifications — tenant + user scoped feed (RUN 2).

Emitted server-side by domain events (award decided, approval decided, invoice
approved, contract expiring, price anomaly opened, qualification decided).
Delivery is honest polling (bell polls /notifications/unread-count every 30s);
realtime push (websocket) is a documented later step, never faked here.

Read state is per-recipient. Directed rows (`user_sub` set) use `read_at`.
Broadcast rows (`user_sub=""`) are seen by the whole tenant, so their read state
lives in `read_by` — otherwise the first person to click would silence the
alert for everyone.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class Notification(Base, TenantMixin):
    __tablename__ = "notifications"

    user_sub: Mapped[str] = mapped_column(String(256), default="", nullable=False)  # "" = whole-tenant broadcast
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    link: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    read_at: Mapped[str] = mapped_column(String(40), default="", nullable=False)  # ISO or "" = unread
    read_by: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (Index("ix_notif_tenant_user", "tenant_id", "user_sub"),)

    def is_read_for(self, sub: str) -> bool:
        """Read state as *this* recipient sees it."""
        if self.user_sub:
            return self.read_at != ""
        return sub in (self.read_by or [])
