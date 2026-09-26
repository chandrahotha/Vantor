"""Price intelligence — 09 PO Price Intelligence Engine (spec 09_POPRICE).

Baseline: median approved-invoice unit price for the same normalized item
(description lowercased/stripped + supplier + UOM) — resistant to outliers,
unlike means. Minimum 3 history points or the baseline is refused (no thin
evidence). Variance in basis points vs baseline; |variance| ≥ 1000bp (10%)
opens an anomaly case with the decomposition (baseline, quoted, delta).
Cases route to sourcing handoff or dismissal with reason — both audited.
"""
from __future__ import annotations

import re
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.purchase import Invoice, InvoiceLine, PurchaseOrderLine

MIN_HISTORY = 3
ANOMALY_BP = 1000


class PriceIntelError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def normalize_item(description: str) -> str:
    return re.sub(r"\s+", " ", (description or "").strip().lower())


def baseline_for(db: Session, *, tenant_id: str, item: str, supplier_id: str, exclude_po_id: str = "") -> dict:
    """Median approved unit price for the same normalized item + supplier.

    History walks approved invoices → their PO lines → PO line descriptions, so
    only like-for-like items form the baseline. The PO under evaluation is
    excluded (a baseline must never contain the price it judges). Raises when
    evidence is thin.
    """
    norm = normalize_item(item)
    if len(norm) < 2:
        raise PriceIntelError("PRICE_ITEM_INVALID", "item description too short for a baseline")
    inv_ids = [i.id for i in db.execute(select(Invoice).where(
        Invoice.tenant_id == tenant_id, Invoice.supplier_id == supplier_id,
        Invoice.status.in_(["approved", "paid"]))).scalars() if i.po_id != exclude_po_id]
    if not inv_ids:
        raise PriceIntelError("PRICE_NO_HISTORY", "no approved invoice history for this supplier")
    po_lines = {l.id: l for l in db.execute(select(PurchaseOrderLine).where(
        PurchaseOrderLine.tenant_id == tenant_id)).scalars()}
    prices: list[int] = []
    for il in db.execute(select(InvoiceLine).where(InvoiceLine.tenant_id == tenant_id, InvoiceLine.invoice_id.in_(inv_ids))).scalars():
        pl = po_lines.get(il.po_line_id)
        if pl is None or normalize_item(pl.description) != norm or il.unit_price_minor <= 0:
            continue
        prices.append(il.unit_price_minor)
    if len(prices) < MIN_HISTORY:
        raise PriceIntelError("PRICE_THIN_HISTORY", f"only {len(prices)} like-for-like points (< {MIN_HISTORY})")
    return {"baseline_minor": int(median(sorted(prices))), "samples": len(prices)}


def variance_bp(*, baseline_minor: int, quoted_minor: int) -> int:
    if baseline_minor <= 0:
        raise PriceIntelError("PRICE_BASELINE_INVALID", "baseline must be positive")
    return round((quoted_minor - baseline_minor) / baseline_minor * 10_000)
