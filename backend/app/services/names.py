"""Batch id -> display-name resolution for cross-entity links in API responses.

Every list/detail endpoint that returns a foreign key (`supplier_id`,
`category_id`, ...) resolves the referenced row's display name here too, so
the frontend never has to show a bare id or re-fetch it separately. One
query per entity type per call, never one query per row — callers collect
every id they need across a page of rows first, then call these once.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.supplier import Category, Supplier


def supplier_names(db: Session, tenant_id: str, ids: set[str | None]) -> dict[str, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {row[0]: row[1] for row in db.execute(
        select(Supplier.id, Supplier.name).where(
            Supplier.tenant_id == tenant_id, Supplier.id.in_(wanted))).all()}


def category_names(db: Session, tenant_id: str, ids: set[str | None]) -> dict[str, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {row[0]: row[1] for row in db.execute(
        select(Category.id, Category.name).where(
            Category.tenant_id == tenant_id, Category.id.in_(wanted))).all()}
