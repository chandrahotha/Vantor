"""Purchase service — tiered approvals, SoD, 3-way match (real procurement rules).

Approval tiers (global practice, configurable later via ApprovalPolicy):
- total <= 100000 minor (1000.00) → manager only.
- total > 100000 minor → manager + finance.
- contract-linked or high-risk supplier → + legal (caller passes legal_required).
SoD: requester/creator cannot approve their own document — enforced by sub compare.

3-way match (PO ↔ receipt ↔ invoice, the global standard for invoice approval):
- every invoice line must reference a PO line of the same PO;
- cumulative already-approved invoiced qty + this invoice's qty <= received qty
  per PO line, and received qty <= ordered qty (both enforced under a row lock
  on the purchase order — see `three_way_match`);
- invoice unit price per PO line == PO unit price (no silent repricing);
- invoice total == sum of lines.
Returns match detail or raises with explicit mismatches (never auto-adjust).
"""
from __future__ import annotations

from sqlalchemy import func, select
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
    """The canonical three-way match. This is the only function that decides
    whether an invoice may become money.

    Three things make it correct, and all three were missing (VNT-001):

    1. **It reads every *other* invoice already approved against the PO** and
       folds them into a cumulative per-line quantity. The old code compared
       only the current invoice's quantity against the received total, so the
       same 100 units received could be invoiced as 60 and then 60 again, both
       passing, both writing an `actual` ledger row. The engine in
       `services.matching` already knew how to take prior lines; the money path
       simply never called it.

    2. **It evaluates through `matching.evaluate()`** rather than re-implementing
       the rules. There were two matchers in this codebase enforcing different
       versions of the same policy, which the workkit's CANONICAL_SERVICE_RULE
       forbids. Now there is one engine and this is its only money-path caller.

    3. **It takes a row lock on the purchase order first.** The cumulative
       comparison is a read of other invoices followed by a write, so without
       serialisation two approvals can both read `prior = 60` and both decide
       `60 + 60 <= 100`. Locking the PO row makes invoice approval, receipting
       and budget-gated PO approval contend on one row per PO, in a deterministic
       order, for the life of the transaction.

    On SQLite (the unit-test harness) `with_for_update()` renders no clause —
    SQLite has no row locks — so the lock is only proven on PostgreSQL by
    `tests/test_pg_concurrency.py`. The cumulative arithmetic is proven
    everywhere by `tests/test_three_way_match.py`.
    """
    from ..models.purchase import (Invoice, InvoiceLine, PurchaseOrder,
                                   PurchaseOrderLine, Receipt, ReceiptLine)
    from .matching import evaluate

    # (3) Serialisation boundary. Also re-reads the PO under the lock, so the
    # status checked here is the committed one, not a pre-lock snapshot.
    po = db.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.id == po_id)
        .with_for_update()
    ).scalar_one_or_none()
    if po is None:
        raise PurchaseError("MATCH_NO_PO", f"Purchase order {po_id} not found")

    po_lines = list(db.execute(
        select(PurchaseOrderLine)
        .where(PurchaseOrderLine.tenant_id == tenant_id, PurchaseOrderLine.po_id == po_id)
        .order_by(PurchaseOrderLine.line_no)).scalars())
    if not po_lines:
        raise PurchaseError("MATCH_NO_PO_LINES", "PO has no lines to match against")

    # Cumulative goods received, per PO line, across every receipt.
    receipt_ids = list(db.execute(
        select(Receipt.id).where(Receipt.tenant_id == tenant_id, Receipt.po_id == po_id)).scalars())
    received: dict[str, int] = {}
    if receipt_ids:
        for line_id, qty in db.execute(
                select(ReceiptLine.po_line_id, func.coalesce(func.sum(ReceiptLine.quantity), 0))
                .where(ReceiptLine.tenant_id == tenant_id, ReceiptLine.receipt_id.in_(receipt_ids))
                .group_by(ReceiptLine.po_line_id)).all():
            received[str(line_id)] = int(qty)

    inv = db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant_id, Invoice.id == invoice_id)).scalar_one_or_none()
    if inv is None:
        raise PurchaseError("MATCH_NO_INVOICE", f"Invoice {invoice_id} not found")
    inv_lines = list(db.execute(
        select(InvoiceLine).where(InvoiceLine.tenant_id == tenant_id,
                                  InvoiceLine.invoice_id == invoice_id)).scalars())
    if not inv_lines:
        raise PurchaseError("MATCH_NO_INVOICE_LINES", "Invoice has no lines")

    # (1) Every OTHER invoice on this PO, with the lines that are already
    # approved. An invoice that was filed but never approved has consumed no
    # money and must not consume ordered quantity either — only `approved` and
    # `paid` count, which is what makes a rejected invoice re-submittable
    # instead of permanently poisoning its PO line.
    prior_invoice_ids = list(db.execute(
        select(Invoice.id).where(
            Invoice.tenant_id == tenant_id, Invoice.po_id == po_id,
            Invoice.id != invoice_id, Invoice.status.in_(("approved", "paid")))).scalars())
    prior_lines: list[dict] = []
    prior_approved: dict[str, int] = {}
    if prior_invoice_ids:
        for il in db.execute(
                select(InvoiceLine.po_line_id, InvoiceLine.quantity, InvoiceLine.unit_price_minor)
                .where(InvoiceLine.tenant_id == tenant_id,
                       InvoiceLine.invoice_id.in_(prior_invoice_ids))).all():
            line_id, qty, price = str(il[0]), int(il[1]), int(il[2])
            prior_lines.append({"po_line_id": line_id, "quantity": qty, "unit_price_minor": price})
            prior_approved[line_id] = prior_approved.get(line_id, 0) + qty

    # (2) One engine, all inputs. `received` and `prior_approved` are what turn
    # the `quantities` dimension into the real three-way invariant.
    result = evaluate(
        contract={"supplier_id": po.supplier_id, "currency": po.currency, "value_minor": po.total_minor},
        po={"supplier_id": po.supplier_id, "currency": po.currency, "lines": [
            {"po_line_id": l.id, "quantity": l.quantity, "unit_price_minor": l.unit_price_minor,
             "line_total_minor": l.line_total_minor} for l in po_lines]},
        invoice={"supplier_id": inv.supplier_id, "currency": inv.currency, "lines": [
            {"po_line_id": l.po_line_id, "quantity": l.quantity, "unit_price_minor": l.unit_price_minor,
             "line_total_minor": l.line_total_minor} for l in inv_lines]},
        prior_invoice_lines=prior_lines,
        po_line_quantities={l.id: l.quantity for l in po_lines},
        received_quantities=received,
        prior_approved_quantities=prior_approved,
    )
    if result["overall"] != "CLEAN":
        failed = [c for c in result["cells"] if c["status"] == "fail"]
        raise PurchaseError(
            "MATCH_FAILED", "Three-way match failed",
            {"mismatches": [{"dimension": c["dim"], "error": c["detail"]} for c in failed],
             "verdictHash": result["hash"]})

    # The dimensions the advisory endpoint cannot see. Surfaced so the audit
    # event records *why* the money was allowed, not just that it was.
    return {
        "matched_lines": len(inv_lines),
        "po_lines": len(po_lines),
        "receivedQuantities": received,
        "priorApprovedQuantities": prior_approved,
        "verdictHash": result["hash"],
    }
