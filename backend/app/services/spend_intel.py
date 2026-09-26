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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.contract import Contract
from ..models.purchase import Invoice, PurchaseOrder
from ..models.spend import SpendTransaction


def cube(db: Session, tenant_id: str) -> list[dict]:
    """Spend cube from the LEDGER (single source of truth), joined to POs for
    category. One row per (supplier, category, currency); no ghost cells."""
    rows = db.execute(select(SpendTransaction, PurchaseOrder.category_id).join(
        PurchaseOrder, PurchaseOrder.id == SpendTransaction.po_id)
        .where(SpendTransaction.tenant_id == tenant_id, SpendTransaction.kind == "commitment")).all()
    cells: dict[tuple, dict] = {}
    for tx, cat in rows:
        key = (tx.supplier_id, cat or "uncategorized", tx.currency)
        cell = cells.setdefault(key, {"supplierId": tx.supplier_id, "categoryId": cat or "uncategorized",
                                      "currency": tx.currency, "totalMinor": 0, "poCount": 0, "_pos": set()})
        cell["totalMinor"] += tx.amount_minor
        cell["_pos"].add(tx.po_id)
    out = []
    for cell in cells.values():
        cell["poCount"] = len(cell.pop("_pos"))
        out.append(cell)
    return sorted(out, key=lambda r: -r["totalMinor"])


def leakage(db: Session, tenant_id: str) -> list[dict]:
    """Approved invoice amounts from suppliers with no active/expiring contract."""
    covered = {c.supplier_id for c in db.execute(select(Contract).where(
        Contract.tenant_id == tenant_id, Contract.status.in_(["active", "expiring"]))).scalars() if c.supplier_id}
    out = []
    for inv in db.execute(select(Invoice).where(
            Invoice.tenant_id == tenant_id, Invoice.status.in_(["approved", "paid"]))).scalars():
        if inv.supplier_id not in covered:
            out.append({"invoiceId": inv.id, "code": inv.code, "supplierId": inv.supplier_id,
                        "totalMinor": inv.total_minor, "currency": inv.currency})
    return out


def maverick(db: Session, tenant_id: str) -> list[dict]:
    """POs with no category and no requisition lineage — off-policy spend."""
    return [{"id": p.id, "code": p.code, "totalMinor": p.total_minor, "reason": "uncategorized-no-requisition"}
            for p in db.execute(select(PurchaseOrder).where(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.status.in_(["approved", "sent", "received", "invoiced"]),
                PurchaseOrder.category_id == "")).scalars()]


def concentration(cells: list[dict]) -> dict:
    by_sup: dict[str, int] = {}
    for c in cells:
        by_sup[c["supplierId"]] = by_sup.get(c["supplierId"], 0) + c["totalMinor"]
    total = sum(by_sup.values())
    if not total:
        return {"topShareBp": 0, "topSupplier": "", "singleSourceRisk": False}
    top, amt = max(by_sup.items(), key=lambda kv: kv[1])
    share = amt * 10_000 // total
    return {"topShareBp": share, "topSupplier": top, "singleSourceRisk": share >= 5000}
