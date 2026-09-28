"""SQLAlchemy base + tenant mixin (every row carries tenant + audit columns)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def tenant_ref(child_table: str, col: str, parent_table: str) -> ForeignKeyConstraint:
    """The composite reference every link in this schema is expressed with.

    A single-column `FOREIGN KEY (supplier_id) REFERENCES suppliers(id)` only
    proves the parent row exists. It does not prove it belongs to the *same
    tenant*, so a supplier contact could be attached to another tenant's supplier
    and every read scoped by `tenant_id` would then return a row whose parent is
    invisible. The constraint has to carry `tenant_id` too:

        FOREIGN KEY (tenant_id, supplier_id) REFERENCES suppliers (tenant_id, id)

    which the database can only accept when the two tenants match, because it
    also enforces that the parent carries both a matching `tenant_id` and the
    named id. That is enforced by the database rather than by a Python check
    that one code path can forget to call.

    `RESTRICT` in both directions matches the rest of the schema: a parent with
    a child is never deleted, and a link is removed by unlinking the child.

    This is the same table of truth as alembic `0019_foreign_keys.py`; the
    assertion that the two agree is `test_tenant_fks_match_migration_0019`.
    """
    return ForeignKeyConstraint(
        ["tenant_id", col],
        [f"{parent_table}.tenant_id", f"{parent_table}.id"],
        name=f"fk_{child_table}_{col}",
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def tenant_key(table: str) -> Index:
    """`UNIQUE (tenant_id, id)` — the index a composite reference points at.

    Redundant as a uniqueness claim (the primary key on `id` already makes the
    pair unique) and present only so a composite `FOREIGN KEY` has something to
    reference. It is added to parent tables only, matching `0019_foreign_keys`.

    Declared as a unique **Index** rather than a `UniqueConstraint` because that
    is what the migration creates (`CREATE UNIQUE INDEX ... ON parent
    (tenant_id, id)`). Alembic's autogenerate treats a unique index and a unique
    constraint as different objects and reports the pair as
    `remove_index` + `add_constraint` on every parent, which is a difference in
    how the ORM is written, not in the schema.
    """
    return Index(f"uq_{table}_tenant_id_id", "tenant_id", "id", unique=True)


class Base(DeclarativeBase):
    pass


class TenantMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
