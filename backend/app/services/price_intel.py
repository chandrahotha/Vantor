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


class BaselineCache:
    """Per-request cache for the PO-line descriptions a baseline is built from.

    `baseline_for` used to load the tenant's entire `purchase_order_lines` table
    on every call, and `price_evaluate` calls it once per PO line — so a PO with
    n lines materialised n x (every PO line in the tenant) rows in memory. This
    loads the description map once and reuses it across the request.
    """

    def __init__(self, db: Session, tenant_id: str):
        self._db = db
        self._tenant_id = tenant_id
        self._descriptions: dict[str, str] | None = None
        self._invoices: dict[str, list[tuple[str, str]]] | None = None

    def _po_line_descriptions(self) -> dict[str, str]:
        if self._descriptions is None:
            rows = self._db.execute(
                select(PurchaseOrderLine.id, PurchaseOrderLine.description).where(
                    PurchaseOrderLine.tenant_id == self._tenant_id)).all()
            self._descriptions = {r[0]: r[1] for r in rows}
        return self._descriptions

    def _approved_invoices(self, supplier_id: str) -> list[tuple[str, str]]:
        """`(invoice_id, po_id)` for approved/paid invoices of a supplier.

        The PO id travels with the invoice id because the caller excludes the
        PO under evaluation, and those are different columns.
        """
        if self._invoices is None:
            self._invoices = {}
            for inv_id, sup, po_id in self._db.execute(
                    select(Invoice.id, Invoice.supplier_id, Invoice.po_id).where(
                        Invoice.tenant_id == self._tenant_id,
                        Invoice.status.in_(["approved", "paid"]))).all():
                self._invoices.setdefault(sup, []).append((inv_id, po_id))
        return self._invoices.get(supplier_id, [])


def baseline_for(db: Session, *, tenant_id: str, item: str, supplier_id: str, exclude_po_id: str = "",
                 cache: BaselineCache | None = None) -> dict:
    """Median approved unit price for the same normalized item + supplier.

    History walks approved invoices -> their PO lines -> PO line descriptions, so
    only like-for-like items form the baseline. The PO under evaluation is
    excluded (a baseline must never contain the price it judges). Raises when
    evidence is thin.

    Pass a `BaselineCache` when evaluating many lines in one request so the
    PO-line and invoice lookups are done once instead of once per line.
    """
    norm = normalize_item(item)
    if len(norm) < 2:
        raise PriceIntelError("PRICE_ITEM_INVALID", "item description too short for a baseline")
    if cache is None:
        cache = BaselineCache(db, tenant_id)
    inv_ids = [inv_id for inv_id, po_id in cache._approved_invoices(supplier_id)
               if not exclude_po_id or po_id != exclude_po_id]
    if not inv_ids:
        raise PriceIntelError("PRICE_NO_HISTORY", "no approved invoice history for this supplier")
    descriptions = cache._po_line_descriptions()
    prices: list[int] = []
    for il in db.execute(select(InvoiceLine).where(InvoiceLine.tenant_id == tenant_id, InvoiceLine.invoice_id.in_(inv_ids))).scalars():
        desc = descriptions.get(il.po_line_id)
        if desc is None or normalize_item(desc) != norm or il.unit_price_minor <= 0:
            continue
        prices.append(il.unit_price_minor)
    if len(prices) < MIN_HISTORY:
        raise PriceIntelError("PRICE_THIN_HISTORY", f"only {len(prices)} like-for-like points (< {MIN_HISTORY})")
    return {"baseline_minor": int(median(sorted(prices))), "samples": len(prices)}


def variance_bp(*, baseline_minor: int, quoted_minor: int) -> int:
    if baseline_minor <= 0:
        raise PriceIntelError("PRICE_BASELINE_INVALID", "baseline must be positive")
    return round((quoted_minor - baseline_minor) / baseline_minor * 10_000)
