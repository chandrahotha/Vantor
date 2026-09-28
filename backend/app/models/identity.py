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
    # VNT-024. The IANA zone this tenant's business day runs in, empty meaning
    # "inherit the deployment's `CONTRACT_TIMEZONE`".
    #
    # "Within 90 days" is a judgement made in the buyer's working day, and a
    # deployment-wide setting gets that wrong for every tenant that is not at the
    # operator's longitude: a buyer at UTC-12 reaches their own 1 January twelve
    # hours before a UTC server does, so a renewal notice fires a day early or a
    # day late. Per-tenant is the only correct granularity - the tenants are in
    # different countries, which is the normal case for the thing being bought.
    timezone: Mapped[str] = mapped_column(String(64), default="", nullable=False)

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
