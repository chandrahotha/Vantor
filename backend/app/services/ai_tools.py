"""Typed AI tools — the ONLY way AI touches data (ADR-004).

No raw SQL, no shell, no direct DB. Each tool is tenant-scoped (actor's tenant
only), permission-checked (roles), deterministic, and audited as AI_TOOL_EXECUTED
with evidence refs. Wave 1 tools are read-only; mutating tools (create_rfq,
request_approval) arrive with HITL gates in Wave 2.
"""
from __future__ import annotations

from sqlalchemy import func, select
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
}

TOOL_REQUIRED_ARGS: dict[str, set[str]] = {
    "search_suppliers": {"q"},
    "get_supplier": {"supplier_id"},
    "compare_quotes": {"rfq_id"},
    "calculate_savings": set(),
    "get_purchase_orders": set(),
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
    return {"suppliers": [{"id": r.id, "code": r.code, "name": r.name, "status": r.status} for r in rows]}


def get_supplier(db: Session, tenant_id: str, supplier_id: str) -> dict:
    r = db.execute(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.id == supplier_id)).scalar_one_or_none()
    if r is None:
        raise ToolError("NOT_FOUND", "Supplier not found in this tenant")
    return {"id": r.id, "code": r.code, "name": r.name, "status": r.status, "country": r.country, "currency": r.currency}


def compare_quotes(db: Session, tenant_id: str, rfq_id: str) -> dict:
    r = db.execute(select(Rfq).where(Rfq.tenant_id == tenant_id, Rfq.id == rfq_id)).scalar_one_or_none()
    if r is None:
        raise ToolError("NOT_FOUND", "RFQ not found in this tenant")
    quotes = list(db.execute(select(Quote).where(Quote.tenant_id == tenant_id, Quote.rfq_id == rfq_id).order_by(Quote.total_minor)).scalars())
    return {"rfq": r.code, "currency": r.currency,
            "quotes": [{"supplierId": q.supplier_id, "status": q.status, "totalMinor": q.total_minor} for q in quotes]}


def calculate_savings(db: Session, tenant_id: str) -> dict:
    from ..models.spend import SavingsRecord

    total = db.execute(select(func.sum(SavingsRecord.saved_minor)).where(SavingsRecord.tenant_id == tenant_id)).scalar() or 0
    n = db.execute(select(func.count()).select_from(SavingsRecord).where(SavingsRecord.tenant_id == tenant_id)).scalar() or 0
    return {"savedMinor": int(total), "awards": int(n)}


def get_purchase_orders(db: Session, tenant_id: str, status: str = "", limit: int = 10) -> dict:
    stmt = select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    rows = list(db.execute(stmt.order_by(PurchaseOrder.created_at.desc()).limit(max(1, min(limit, 25)))).scalars())
    return {"orders": [{"id": p.id, "code": p.code, "status": p.status, "totalMinor": p.total_minor} for p in rows]}


REGISTRY = {
    "search_suppliers": search_suppliers,
    "get_supplier": get_supplier,
    "compare_quotes": compare_quotes,
    "calculate_savings": calculate_savings,
    "get_purchase_orders": get_purchase_orders,
}
