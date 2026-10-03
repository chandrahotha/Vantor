"""Spend intelligence — 07 (spec 07_SPENDINTEL): cube, leakage, maverick, concentration.

- Cube: spend by (supplier × category × period) from the ledger (commitments) —
  explicit zeros when empty, never synthetic.
- Leakage: approved-invoice totals NOT covered by an active contract for the
  same supplier (contract coverage gap = spend without negotiated terms).
- Maverick: POs created by buyers with no requisition linkage... V1 proxy:
  POs with no category (uncategorized spend escapes policy). Reported with amounts.
- Concentration: top-supplier share of committed spend (single-source risk flag
  at >= 50%).
All deterministic, integer math, tenant-scoped.
"""
from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models.contract import Contract
from ..models.purchase import Invoice, PurchaseOrder
from ..models.spend import SpendTransaction
from .names import category_names, supplier_names


def cube(db: Session, tenant_id: str) -> list[dict]:
    """Spend cube from the LEDGER (single source of truth), joined to POs for
    category. One row per (supplier, category, currency); no ghost cells.

    The join is an OUTER join and the tenant predicate lives in the ON clause.
    Two reasons: an inner join silently dropped any ledger row whose PO is
    missing (under-reporting the one number that must never be wrong), and
    without the tenant predicate the join relied on RLS alone for correctness.
    A commitment with no matching PO still lands in the cube, as uncategorized.
    """
    rows = db.execute(select(SpendTransaction, PurchaseOrder.category_id).outerjoin(
        PurchaseOrder, and_(PurchaseOrder.id == SpendTransaction.po_id,
                            PurchaseOrder.tenant_id == tenant_id))
        .where(SpendTransaction.tenant_id == tenant_id, SpendTransaction.kind == "commitment")).all()
    cells: dict[tuple, dict] = {}
    for tx, cat in rows:
        key = (tx.supplier_id, cat or "uncategorized", tx.currency)
        cell = cells.setdefault(key, {"supplierId": tx.supplier_id, "categoryId": cat or "uncategorized",
                                      "currency": tx.currency, "totalMinor": 0, "poCount": 0,
                                      "orphaned": False, "_pos": set()})
        cell["totalMinor"] += tx.amount_minor
        cell["orphaned"] = cell["orphaned"] or cat is None
        if tx.po_id:
            cell["_pos"].add(tx.po_id)
    out = []
    for cell in cells.values():
        cell["poCount"] = len(cell.pop("_pos"))
        out.append(cell)
    sup_names = supplier_names(db, tenant_id, {c["supplierId"] for c in out})
    cat_names = category_names(db, tenant_id, {c["categoryId"] for c in out if c["categoryId"] != "uncategorized"})
    for cell in out:
        cell["supplierName"] = sup_names.get(cell["supplierId"], "")
        cell["categoryName"] = cat_names.get(cell["categoryId"], "") if cell["categoryId"] != "uncategorized" else "Uncategorized"
    return sorted(out, key=lambda r: -r["totalMinor"])


def leakage(db: Session, tenant_id: str) -> list[dict]:
    """Approved invoice amounts from suppliers with no active/expiring contract.

    Done entirely in the database. The previous version loaded every
    approved/paid `Invoice` entity in the tenant into memory and filtered in
    Python, so this report cost total history rather than the (much smaller)
    set of uncovered invoices.
    """
    uncovered = ~Invoice.supplier_id.in_(select(Contract.supplier_id).where(
        Contract.tenant_id == tenant_id,
        Contract.status.in_(["active", "expiring"]),
        Contract.supplier_id != ""))
    rows = db.execute(
        select(Invoice.id, Invoice.code, Invoice.supplier_id, Invoice.total_minor, Invoice.currency)
        .where(Invoice.tenant_id == tenant_id,
               Invoice.status.in_(["approved", "paid"]),
               uncovered).order_by(Invoice.total_minor.desc())).all()
    sup_names = supplier_names(db, tenant_id, {r[2] for r in rows})
    return [{"invoiceId": r[0], "code": r[1], "supplierId": r[2], "supplierName": sup_names.get(r[2], ""),
             "totalMinor": r[3], "currency": r[4]} for r in rows]


def maverick(db: Session, tenant_id: str) -> list[dict]:
    """POs with no category — off-policy spend.

    "No link" is now NULL (0018), not the empty-string sentinel; querying
    `category_id == ""` would now answer "none ever" because it lies in the old
    mechanism rather than the data. NULL is the queryable truth.
    """
    return [{"id": p.id, "code": p.code, "totalMinor": p.total_minor,
             "reason": "uncategorized", "note": "no category set; requisition lineage is not tracked"}
            for p in db.execute(select(PurchaseOrder).where(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.status.in_(["approved", "sent", "received", "invoiced"]),
                PurchaseOrder.category_id.is_(None))).scalars()]


def concentration(cells: list[dict]) -> dict:
    """Top-supplier share of committed spend.

    VNT-UI: `topSupplier` used to be the raw supplier *id* — `by_sup` is keyed
    on `supplierId`, and the id was returned under a field name that reads as
    a display name, so the UI rendered a bare UUID inline in a risk message.
    `cube()` now attaches `supplierName` to every cell, so the name is read
    from there rather than re-queried; `topSupplierId` is kept for linking.
    """
    by_sup: dict[str, int] = {}
    names: dict[str, str] = {}
    for c in cells:
        sid = c["supplierId"]
        by_sup[sid] = by_sup.get(sid, 0) + c["totalMinor"]
        if c.get("supplierName"):
            names[sid] = c["supplierName"]
    total = sum(by_sup.values())
    if not total:
        return {"topShareBp": 0, "topSupplierId": "", "topSupplierName": "", "singleSourceRisk": False}
    top, amt = max(by_sup.items(), key=lambda kv: kv[1])
    share = amt * 10_000 // total
    return {"topShareBp": share, "topSupplierId": top, "topSupplierName": names.get(top, ""), "singleSourceRisk": share >= 5000}
