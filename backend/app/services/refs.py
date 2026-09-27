"""Updated refs helpers: NULL is the "no link" value, not "".

The schema used "" = "no link". With FKs, `""` has to become NULL, because no
parent row has id="". `require_ref` therefore maps a falsy input to None and
returns None for a valid one — a nullable column stores None, a mandatory one
must not be called with "" anyway.
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


def require_ref(db: Session, model: type[M], tenant_id: str, ref_id: str | None,
                *, field: str, code: str = "UNKNOWN_REFERENCE") -> str | None:
    """Return the linked id, or None when the caller means "no link".

    An empty string is no longer a sentinel for "no link" — a NULL foreign key
    is. A non-empty id must reference an existing row in this tenant.
    """
    value = (ref_id or "").strip()
    if not value:
        return None
    if not _exists(db, model, tenant_id, value):
        raise HTTPException(status_code=422, detail={
            "code": code,
            "message": f"{field} does not reference an existing record in this tenant",
            "details": {"field": field, "value": value},
        })
    return value


def require_refs(db: Session, model: type[M], tenant_id: str, ref_ids: list[str | None],
                 *, field: str, code: str = "UNKNOWN_REFERENCE") -> list[str | None]:
    values = [(r or "").strip() or None for r in ref_ids]
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


def require_no_cycle(db: Session, model: type[M], tenant_id: str, ref_id: str | None, *,
                     field: str = "parent_id", max_depth: int = 32) -> str | None:
    """Validate a self-referencing parent, refusing cycles and runaway depth."""
    value = require_ref(db, model, tenant_id, ref_id, field=field, code="REFERENCE_CYCLE")
    if value is None:
        return None
    seen: set[str] = {value}
    cursor: str | None = value
    depth = 0
    while cursor:
        row = db.execute(
            select(model).where(model.tenant_id == tenant_id, model.id == cursor)  # type: ignore[attr-defined]
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=422, detail={
                "code": "UNKNOWN_REFERENCE",
                "message": f"{field} does not reference an existing record in this tenant",
                "details": {"field": field, "value": cursor},
            })
        cursor = (getattr(row, field, None) or "").strip() or None
        if cursor in seen:
            raise HTTPException(status_code=422, detail={
                "code": "REFERENCE_CYCLE",
                "message": f"{field} would create a cycle",
                "details": {"field": field, "value": value},
            })
        depth += 1
        if depth > max_depth:
            raise HTTPException(status_code=422, detail={
                "code": "REFERENCE_TOO_DEEP",
                "message": f"{field} exceeds the maximum depth ({max_depth})",
            })
    return value
