"""Supplier + catalog models — Phase 4 Core Wave 2.1 (canonical merge of 5 shapes).

One `suppliers` table (provenance columns kept for migration), one `categories`
table. No fake rows, no seeds of suppliers — reference categories only via API.
Lifecycle: draft → active → on_hold → blocked → archived.
"""
from __future__ import annotations

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin

SUPPLIER_STATUSES = {"draft", "active", "on_hold", "blocked", "archived"}


class Category(Base, TenantMixin):
    __tablename__ = "categories"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_cat_tenant_code"),)


class Supplier(Base, TenantMixin):
    __tablename__ = "suppliers"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    country: Mapped[str] = mapped_column(String(2), default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    category_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    payment_terms: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    source_repo: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    source_commit: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_supplier_tenant_code"),
        Index("ix_supplier_tenant_status", "tenant_id", "status"),
        Index("ix_supplier_tenant_name", "tenant_id", "name"),
    )


class SupplierContact(Base, TenantMixin):
    __tablename__ = "supplier_contacts"

    supplier_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    __table_args__ = (Index("ix_contact_tenant_supplier", "tenant_id", "supplier_id"),)
