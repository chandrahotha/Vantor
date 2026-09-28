"""Contract models — Phase 4 Wave 2.3 (repository + obligations + renewals).

Lifecycle (per domain): draft → review → active → expiring → renewed | expired.
`expiring` is server-derived (end_date within 90 days) but stored for grid
filtering; transitions validated — never client-faked.
Matching engine (ContractGuard 11-dim) lands as a deterministic service next;
repository here is the system of record it will score against.
"""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, tenant_key, tenant_ref

CONTRACT_STATUSES = {"draft", "review", "active", "expiring", "renewed", "expired", "terminated"}
OBLIGATION_STATUSES = {"open", "done", "overdue", "waived"}


class Contract(Base, TenantMixin):
    __tablename__ = "contracts"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    contract_type: Mapped[str] = mapped_column(String(64), default="supply", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    value_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_date: Mapped[str] = mapped_column(String(10), default="", nullable=False)  # ISO YYYY-MM-DD
    end_date: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_contract_tenant_code"),
        Index("ix_contract_tenant_status", "tenant_id", "status"),
        Index("ix_contract_tenant_end", "tenant_id", "end_date"),

        # Composite, tenant-carrying links — this table is referenced by a composite link and itself linked by a composite reference.
        tenant_key("contracts"),
        tenant_ref("contracts", "supplier_id", "suppliers"),
    )


class ContractObligation(Base, TenantMixin):
    __tablename__ = "contract_obligations"

    contract_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    due_date: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    owner: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    __table_args__ = (
        Index("ix_oblig_tenant_contract", "tenant_id", "contract_id"),

        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("contract_obligations", "contract_id", "contracts"),
    )
