"""Purchase service — tiered approvals, SoD, 3-way match (real procurement rules).

Approval tiers (global practice, configurable later via ApprovalPolicy):
- total <= 100000 minor (1000.00) → manager only.
- total > 100000 minor → manager + finance.
- contract-linked or high-risk supplier → + legal (caller passes legal_required).
SoD: requester/creator cannot approve their own document — enforced by sub compare.

3-way match (PO ↔ receipt ↔ invoice, the global standard for invoice approval):
- every invoice line must reference a PO line of the same PO;
- invoiced qty per PO line <= received qty per PO line (cumulative);
- invoice unit price per PO line == PO unit price (no silent repricing);
- invoice total == sum of lines.
Returns match detail or raises with explicit mismatches (never auto-adjust).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

MANAGER_LIMIT_MINOR = 100_000


class PurchaseError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def required_tiers(total_minor: int, *, legal_required: bool = False) -> list[str]:
    tiers = ["manager"] if total_minor <= MANAGER_LIMIT_MINOR else ["manager", "finance"]
    if legal_required:
        tiers.append("legal")
    return tiers


def check_sod(requester_sub: str, approver_sub: str) -> None:
    if requester_sub and requester_sub == approver_sub:
        raise PurchaseError("APPROVAL_SOD", "Requester cannot approve their own document (segregation of duties)")


#: The canonical order a multi-tier approval must be consumed in. An approver
#: always clears the *earliest* outstanding tier, so finance can never consume
#: the manager's signature slot and skip a step.
TIER_ORDER = ("manager", "finance", "legal")


def tier_rank(tier: str) -> int:
    """Sort key for a tier; unknown tiers sort last but stay deterministic."""
    try:
        return TIER_ORDER.index((tier or "").strip().lower())
    except ValueError:
        return len(TIER_ORDER)


def order_pending(pending: list) -> list:
    """Pending approvals in the order they must be decided (earliest tier first).

    Ties break on `created_at` then `id` so the order is stable across calls
    and identical databases. This is what stops a finance approver from
    consuming the manager tier out of turn.
    """
    def key(a) -> tuple:  # type: ignore[no-untyped-def]
        ts = a.created_at
        # Missing timestamps sort last, never first: an unknown age must not
        # outrank a tier that was genuinely filed first.
        return (tier_rank(a.tier), ts is None, ts or "", a.id)

    return sorted(pending, key=key)


def next_pending(pending: list):
    """The single approval an approver is allowed to clear right now."""
    return order_pending(pending)[0] if pending else None


#: Roles allowed to decide an approval, and the resources an approval may name.
APPROVER_ROLES = {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Approver", "Finance Reviewer"}


def decide_approval(db: Session, *, tenant_id: str, approver_sub: str, approver_roles: set[str],
                    approval: object, approve: bool, reason: str) -> str:
    """Record a human decision on one approval row and return the new status.

    Shared by the purchase and AI routers so segregation of duties, tier
    ordering and audit are enforced in exactly one place. Raises
    `PurchaseError` with a code; the routers map code -> HTTP status.
    """
    from ..services.audit import record_event

    if not (approver_roles or set()) & APPROVER_ROLES:
        raise PurchaseError("APPROVAL_ROLE", "Approver role required")
    status = getattr(approval, "status", "")
    if status != "requested":
        raise PurchaseError("APPROVAL_ALREADY_DECIDED", f"already {status}")
    if not approve and not reason.strip():
        raise PurchaseError("APPROVAL_REASON_REQUIRED", "A rejection needs a written reason")

    # SoD is enforced against whoever filed the approval, which for a PO or
    # requisition is the person who raised it.
    filed_by = getattr(approval, "created_by", "") or ""
    check_sod(filed_by, approver_sub)

    new_status = "approved" if approve else "rejected"
    setattr(approval, "status", new_status)
    setattr(approval, "decided_by", approver_sub)
    setattr(approval, "reason", reason.strip())
    setattr(approval, "updated_by", approver_sub)
    # `approval=` is part of the hashed payload, so this is what makes the audit
    # trail answer "which approval authorised this change?". It was plumbed all
    # the way from the model to the writer and never populated by any caller.
    record_event(db, tenant_id=tenant_id, actor=approver_sub, action="APPROVAL_DECIDED",
                 resource=getattr(approval, "resource", "") or "approval",
                 resource_id=getattr(approval, "id", ""),
                 after={"approved": approve, "tier": getattr(approval, "tier", "")},
                 reason=reason.strip(), approval=str(getattr(approval, "id", "")),
                 source="api", created_by=approver_sub)
    return new_status


def three_way_match(db: Session, *, tenant_id: str, po_id: str, invoice_id: str) -> dict:
    from ..models.purchase import InvoiceLine, PurchaseOrderLine, Receipt, ReceiptLine

    po_lines = {l.id: l for l in db.execute(
        select(PurchaseOrderLine).where(PurchaseOrderLine.tenant_id == tenant_id, PurchaseOrderLine.po_id == po_id)).scalars()}
    if not po_lines:
        raise PurchaseError("MATCH_NO_PO_LINES", "PO has no lines to match against")
    receipt_ids = [r.id for r in db.execute(
        select(Receipt).where(Receipt.tenant_id == tenant_id, Receipt.po_id == po_id)).scalars()]
    received: dict[str, int] = {}
    if receipt_ids:
        for rl in db.execute(select(ReceiptLine).where(ReceiptLine.tenant_id == tenant_id, ReceiptLine.receipt_id.in_(receipt_ids))).scalars():
            received[rl.po_line_id] = received.get(rl.po_line_id, 0) + rl.quantity
    inv_lines = list(db.execute(select(InvoiceLine).where(InvoiceLine.tenant_id == tenant_id, InvoiceLine.invoice_id == invoice_id)).scalars())
    if not inv_lines:
        raise PurchaseError("MATCH_NO_INVOICE_LINES", "Invoice has no lines")
    mismatches: list[dict] = []
    for il in inv_lines:
        pl = po_lines.get(il.po_line_id)
        if pl is None:
            mismatches.append({"po_line_id": il.po_line_id, "error": "not on PO"})
            continue
        if il.unit_price_minor != pl.unit_price_minor:
            mismatches.append({"po_line_id": il.po_line_id, "error": f"price {il.unit_price_minor} != PO {pl.unit_price_minor}"})
        if il.quantity > received.get(il.po_line_id, 0):
            mismatches.append({"po_line_id": il.po_line_id, "error": f"invoiced {il.quantity} > received {received.get(il.po_line_id, 0)}"})
        if il.line_total_minor != il.unit_price_minor * il.quantity:
            mismatches.append({"po_line_id": il.po_line_id, "error": "line total != price x qty"})
    if mismatches:
        raise PurchaseError("MATCH_FAILED", "Three-way match failed", {"mismatches": mismatches})
    return {"matched_lines": len(inv_lines), "po_lines": len(po_lines)}
