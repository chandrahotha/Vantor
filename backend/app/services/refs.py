"""Referential checks for the id columns that carry no database constraint.

There is not one FOREIGN KEY in this schema (see `docs/02-architecture/database.md`),
so `*_id` columns are plain strings and a typo — or another tenant's id — writes
an orphan that only surfaces months later in a cube or a match report. Most
routers already validate their parents inline; the ones that did not share a
single helper, which is why the coverage was uneven.

`require_ref` is that one helper. It is deliberately small and tenant-scoped:
RLS is the backstop, but RLS is not a substitute for saying "that category does
not exist" at the point the caller can still fix it.
"""
from __future__ import annotations

from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

M = TypeVar("M")


def _exists(db: Session, model: type[M], tenant_id: str, ref_id: str) -> bool:
    return db.execute(
        select(model.id).where(model.tenant_id == tenant_id, model.id == ref_id)  # type: ignore[attr-defined]
    ).first() is not None


def require_ref(db: Session, model: type[M], tenant_id: str, ref_id: str, *, field: str, code: str = "UNKNOWN_REFERENCE") -> str:
    """Return the trimmed `ref_id`, or raise 422 naming the field and the parent.

    An empty id is allowed and returned as `""` — several columns use "" to mean
    "deliberately unlinked" (an uncategorised PO, a budget that covers the whole
    tenant). Callers that must have a parent pass `allow_empty=False`.
    """
    value = (ref_id or "").strip()
    if not value:
        return ""
    if not _exists(db, model, tenant_id, value):
        raise HTTPException(status_code=422, detail={
            "code": code,
            "message": f"{field} does not reference an existing record in this tenant",
            "details": {"field": field, "value": value},
        })
    return value


def require_refs(db: Session, model: type[M], tenant_id: str, ref_ids: list[str], *, field: str,
                 code: str = "UNKNOWN_REFERENCE") -> list[str]:
    """Same as `require_ref` for a list; one query, 422 naming the first bad id."""
    values = [(r or "").strip() for r in ref_ids]
    wanted = [v for v in values if v]
    if not wanted:
        return values
    found = set(db.execute(
        select(model.id).where(model.tenant_id == tenant_id, model.id.in_(wanted))  # type: ignore[attr-defined]
    ).scalars())
    for value in values:
        if value and value not in found:
            raise HTTPException(status_code=422, detail={
                "code": code,
                "message": f"{field} does not reference an existing record in this tenant",
                "details": {"field": field, "value": value},
            })
    return values


def require_no_cycle(db: Session, model: type[M], tenant_id: str, ref_id: str, *, field: str = "parent_id",
                     max_depth: int = 32) -> str:
    """Validate a self-referencing parent, refusing cycles and runaway depth.

    `categories.parent_id` is the only self-reference in the schema. A→B→A was
    accepted before this check, and any future walk up the tree would hang.
    """
    value = (ref_id or "").strip()
    if not value:
        return ""
    seen: set[str] = set()
    cursor = value
    depth = 0
    while cursor:
        if cursor in seen:
            raise HTTPException(status_code=422, detail={
                "code": "REFERENCE_CYCLE",
                "message": f"{field} would create a cycle in the category tree",
                "details": {"field": field, "value": value},
            })
        if depth > max_depth:
            raise HTTPException(status_code=422, detail={
                "code": "REFERENCE_TOO_DEEP",
                "message": f"{field} exceeds the maximum category depth ({max_depth})",
                "details": {"field": field, "value": value},
            })
        seen.add(cursor)
        row = db.execute(
            select(model).where(model.tenant_id == tenant_id, model.id == cursor)  # type: ignore[attr-defined]
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=422, detail={
                "code": "UNKNOWN_REFERENCE",
                "message": f"{field} does not reference an existing record in this tenant",
                "details": {"field": field, "value": cursor},
            })
        cursor = (getattr(row, field, "") or "").strip()
        depth += 1
    return value
