"""Typed AI tools — the ONLY way AI touches data (ADR-004).

No raw SQL, no shell, no direct DB. Each tool is tenant-scoped (actor's tenant
only), permission-checked (roles), deterministic, and audited as AI_TOOL_EXECUTED
with evidence refs. Wave 1 tools are read-only; mutating tools (create_rfq,
request_approval) arrive with HITL gates in Wave 2.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.purchase import PurchaseOrder
from ..models.sourcing import Quote, Rfq
from ..models.supplier import Supplier

TOOL_ROLES: dict[str, set[str]] = {
    "search_suppliers": {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer",
                         "Category Manager", "Supplier Manager", "Finance Reviewer", "Legal Reviewer", "Approver", "Auditor", "Read Only"},
    "get_supplier": {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer",
                     "Category Manager", "Supplier Manager", "Finance Reviewer", "Legal Reviewer", "Approver", "Auditor", "Read Only"},
    "compare_quotes": {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer",
                       "Category Manager", "Approver", "Auditor"},
    "calculate_savings": {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer",
                          "Finance Reviewer", "Approver", "Auditor"},
    "get_purchase_orders": {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer",
                            "Finance Reviewer", "Approver", "Auditor"},
    "request_approval": {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Buyer",
                         "Category Manager", "Approver"},
}

TOOL_REQUIRED_ARGS: dict[str, set[str]] = {
    "search_suppliers": {"q"},
    "get_supplier": {"supplier_id"},
    "compare_quotes": {"rfq_id"},
    "calculate_savings": set(),
    "get_purchase_orders": set(),
    "request_approval": {"action", "resource", "resource_id"},
}


class ToolError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def check_tool_access(roles: tuple[str, ...], tool: str) -> None:
    if tool not in REGISTRY:
        raise ToolError("TOOL_UNKNOWN", f"Unknown tool {tool!r}")
    allowed = TOOL_ROLES.get(tool, set())
    if not set(roles or ()) & allowed:
        raise ToolError("TOOL_FORBIDDEN", f"No tool permission for {tool!r}")


def check_tool_args(tool: str, args: dict) -> None:
    missing = TOOL_REQUIRED_ARGS.get(tool, set()) - set((args or {}).keys())
    if missing:
        raise ToolError("TOOL_ARGS_INVALID", f"{tool} missing required args: {sorted(missing)}")


def search_suppliers(db: Session, tenant_id: str, q: str, limit: int = 10) -> dict:
    if len((q or "").strip()) < 2:
        raise ToolError("TOOL_ARGS_INVALID", "search_suppliers.q needs at least 2 characters")
    like = f"%{q.strip()}%"
    rows = list(db.execute(select(Supplier).where(Supplier.tenant_id == tenant_id,
                  (Supplier.name.ilike(like)) | (Supplier.code.ilike(like))).limit(max(1, min(limit, 25)))).scalars())
    return {
        "suppliers": [{"id": r.id, "code": r.code, "name": r.name, "status": r.status} for r in rows],
        # Every claim the copilot makes must trace to a row. The evidence list is
        # how a human (or the eval suite) verifies that.
        "evidence": [{"type": "supplier", "id": r.id, "ref": r.code} for r in rows],
    }


def get_supplier(db: Session, tenant_id: str, supplier_id: str) -> dict:
    r = db.execute(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.id == supplier_id)).scalar_one_or_none()
    if r is None:
        raise ToolError("NOT_FOUND", "Supplier not found in this tenant")
    return {"id": r.id, "code": r.code, "name": r.name, "status": r.status, "country": r.country, "currency": r.currency,
            "evidence": [{"type": "supplier", "id": r.id, "ref": r.code}]}


def compare_quotes(db: Session, tenant_id: str, rfq_id: str) -> dict:
    r = db.execute(select(Rfq).where(Rfq.tenant_id == tenant_id, Rfq.id == rfq_id)).scalar_one_or_none()
    if r is None:
        raise ToolError("NOT_FOUND", "RFQ not found in this tenant")
    quotes = list(db.execute(select(Quote).where(Quote.tenant_id == tenant_id, Quote.rfq_id == rfq_id).order_by(Quote.total_minor)).scalars())
    return {"rfq": r.code, "currency": r.currency,
            "quotes": [{"supplierId": q.supplier_id, "status": q.status, "totalMinor": q.total_minor} for q in quotes],
            "evidence": [{"type": "rfq", "id": r.id, "ref": r.code}] + [{"type": "quote", "id": q.id, "ref": q.supplier_id} for q in quotes]}


def calculate_savings(db: Session, tenant_id: str) -> dict:
    from ..models.spend import SavingsRecord

    rows = list(db.execute(select(SavingsRecord).where(SavingsRecord.tenant_id == tenant_id)).scalars())
    total = sum(r.saved_minor for r in rows)
    return {"savedMinor": int(total), "awards": len(rows),
            "evidence": [{"type": "savings_record", "id": r.id, "ref": r.award_id} for r in rows]}


def get_purchase_orders(db: Session, tenant_id: str, status: str = "", limit: int = 10) -> dict:
    stmt = select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    rows = list(db.execute(stmt.order_by(PurchaseOrder.created_at.desc()).limit(max(1, min(limit, 25)))).scalars())
    return {"orders": [{"id": p.id, "code": p.code, "status": p.status, "totalMinor": p.total_minor} for p in rows],
            "evidence": [{"type": "purchase_order", "id": p.id, "ref": p.code} for p in rows]}


def request_approval(db: Session, tenant_id: str, action: str, resource: str, resource_id: str, reason: str = "", requested_by: str = "") -> dict:
    """HITL gate: file an approval request for a proposed AI-driven action.

    Nothing executes here — a human decides via POST /ai/approvals/{id}/decide
    and the caller performs the action through the normal API afterwards.
    """
    from ..models.purchase import Approval

    if action not in {"award_contract", "approve_purchase", "modify_financials", "contact_supplier", "other"}:
        raise ToolError("TOOL_ARGS_INVALID", "action must be a known high-risk action")
    # `resource` is caller-supplied and Approval.resource is a bounded column.
    # Validate instead of truncating: a silently clipped resource_id would file
    # an approval against the wrong record, which is worse than a 422.
    resource = (resource or "").strip()
    resource_id = (resource_id or "").strip()
    if not resource or len(resource) > 61:
        raise ToolError("TOOL_ARGS_INVALID", "resource must be 1-61 characters")
    if not resource_id or len(resource_id) > 36:
        raise ToolError("TOOL_ARGS_INVALID", "resource_id must be 1-36 characters")
    row = Approval(tenant_id=tenant_id, created_by=requested_by, updated_by=requested_by,
                   resource=f"ai:{resource}", resource_id=resource_id, status="requested",
                   tier="manager", reason=f"{action}: {reason}"[:500])
    db.add(row)
    db.flush()
    return {"approval_id": row.id, "status": "requested", "resource": f"ai:{resource}"}


#: Every callable here takes `(db, tenant_id, **kwargs)` and returns a JSON-able
#: dict. Typing it explicitly is what lets callers index it without a cast.
REGISTRY: dict[str, Callable[..., dict]] = {
    "search_suppliers": search_suppliers,
    "get_supplier": get_supplier,
    "compare_quotes": compare_quotes,
    "calculate_savings": calculate_savings,
    "get_purchase_orders": get_purchase_orders,
    "request_approval": request_approval,
}
