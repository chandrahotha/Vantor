"""Onboarding models — 08 Supplier Onboarding & Qualification (spec 08_SUPPLIERONBOARD).

Certification: evidence docs per supplier (name, issuer, valid_until, status).
Qualification: one case per supplier — draft → submitted → under_review →
qualified | rejected. Qualification requires: ≥1 verified certification AND a
scorecard with grade C or better (evidence-backed, never self-declared).
"""
from __future__ import annotations

from sqlalchemy import Index, String, Text, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, tenant_ref

CERT_STATUSES = {"pending", "verified", "expired", "rejected"}
QUAL_STATUSES = {"draft", "submitted", "under_review", "qualified", "rejected"}


class SupplierCertification(Base, TenantMixin):
    __tablename__ = "supplier_certifications"

    supplier_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    valid_until: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_cert_tenant_supplier", "tenant_id", "supplier_id"),

        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("supplier_certifications", "supplier_id", "suppliers"),
        tenant_ref("supplier_certifications", "document_id", "documents"),
    )


class SupplierQualification(Base, TenantMixin):
    __tablename__ = "supplier_qualifications"

    supplier_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    checklist: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    decided_by: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "supplier_id", name="uq_qual_tenant_supplier"),

        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("supplier_qualifications", "supplier_id", "suppliers"),
    )
