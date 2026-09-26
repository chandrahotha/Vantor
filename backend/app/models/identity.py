"""Identity models — Organization + User + Role (foundation slice).

Full RBAC matrix (spending limits, approval authority) lands with Phase 4;
here: real tables, UUID ids, tenant scoping, no hardcoded roles in code paths.
Seed only reference roles — never fake users or tenants.
"""
from __future__ import annotations

from sqlalchemy import JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class Organization(Base, TenantMixin):
    __tablename__ = "organizations"

    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_org_tenant_slug"),)


class UserAccount(Base, TenantMixin):
    __tablename__ = "user_accounts"

    subject: Mapped[str] = mapped_column(String(256), nullable=False)  # OIDC sub
    email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    roles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "subject", name="uq_user_tenant_sub"),)


class Role(Base, TenantMixin):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),)
