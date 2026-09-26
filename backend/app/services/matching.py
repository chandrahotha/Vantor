"""Contract matching engine — deterministic 11-dimension comparison (ContractGuard pattern).

Compares contract ↔ PO ↔ invoice with integer math only. Each dimension yields
pass/flag/fail; any fail => HOLD with the mismatched amount. The verdict_hash
(sha256 over canonical cells) makes runs reproducible and auditable — same
inputs always produce the same hash. No LLM, no heuristics, no thresholds from
vibes: tolerances are explicit parameters (default zero).
"""
from __future__ import annotations

import hashlib
import json

DIMS = ("parties", "currency", "po_arithmetic", "invoice_arithmetic", "totals",
        "quantities", "prices", "coverage", "period", "line_count", "duplicates")


class MatchError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _canon(cells: list[dict]) -> str:
    return json.dumps(cells, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def verdict_hash(cells: list[dict]) -> str:
    return hashlib.sha256(_canon(cells).encode()).hexdigest()


def evaluate(*, contract: dict, po: dict, invoice: dict, prior_invoice_count: int = 0) -> dict:
    """All amounts integer minor units. Returns {cells, overall, hold_amount_minor, hash}."""
    for doc, name in ((contract, "contract"), (po, "po"), (invoice, "invoice")):
        if not isinstance(doc, dict):
            raise MatchError("MATCH_INPUT_INVALID", f"{name} must be an object")
    cells: list[dict] = []

    def cell(dim: str, status: str, detail: str = "") -> None:
        assert status in {"pass", "flag", "fail"}
        cells.append({"dim": dim, "status": status, "detail": detail})

    # 1 parties
    if contract.get("supplier_id") and contract["supplier_id"] == po.get("supplier_id") == invoice.get("supplier_id"):
        cell("parties", "pass")
    else:
        cell("parties", "fail", "supplier mismatch across documents")
    # 2 currency
    if contract.get("currency") == po.get("currency") == invoice.get("currency") and po.get("currency"):
        cell("currency", "pass")
    else:
        cell("currency", "fail", "currency mismatch or missing")
    # 3 po arithmetic
    po_lines = po.get("lines", [])
    if po_lines and all(isinstance(l, dict) for l in po_lines):
        cell("po_arithmetic", "pass" if all(l.get("unit_price_minor", -1) * l.get("quantity", -1) == l.get("line_total_minor", -2) for l in po_lines) else "fail",
             "" if all(l.get("unit_price_minor", -1) * l.get("quantity", -1) == l.get("line_total_minor", -2) for l in po_lines) else "po line math broken")
    else:
        cell("po_arithmetic", "fail", "no po lines")
    # 4 invoice arithmetic
    inv_lines = invoice.get("lines", [])
    if inv_lines and all(isinstance(l, dict) for l in inv_lines):
        ok = all(l.get("unit_price_minor", -1) * l.get("quantity", -1) == l.get("line_total_minor", -2) for l in inv_lines)
        cell("invoice_arithmetic", "pass" if ok else "fail", "" if ok else "invoice line math broken")
    else:
        cell("invoice_arithmetic", "fail", "no invoice lines")
    po_total = sum(l.get("line_total_minor", 0) for l in po_lines) if po_lines else 0
    inv_total = sum(l.get("line_total_minor", 0) for l in inv_lines) if inv_lines else 0
    # 5 totals
    cell("totals", "pass" if po_total == inv_total and po_total > 0 else "fail", f"po={po_total} inv={inv_total}")
    # 6 quantities (invoice qty <= po qty per matched line index)
    if po_lines and inv_lines and len(inv_lines) <= len(po_lines):
        ok = all(inv_lines[i].get("quantity", 0) <= po_lines[i].get("quantity", -1) for i in range(len(inv_lines)))
        cell("quantities", "pass" if ok else "fail", "" if ok else "invoiced qty exceeds ordered")
    else:
        cell("quantities", "fail", "line alignment impossible")
    # 7 prices
    if po_lines and inv_lines and len(inv_lines) <= len(po_lines):
        ok = all(inv_lines[i].get("unit_price_minor") == po_lines[i].get("unit_price_minor") for i in range(len(inv_lines)))
        cell("prices", "pass" if ok else "fail", "" if ok else "unit price drift vs PO")
    else:
        cell("prices", "fail", "line alignment impossible")
    # 8 coverage (contract value covers PO)
    cval = contract.get("value_minor", 0)
    cell("coverage", "pass" if cval >= po_total > 0 else "flag" if cval == 0 else "fail", f"contract={cval} po={po_total}")
    # 9 period (po within contract window when dates present)
    cs, ce, pd = contract.get("start_date", ""), contract.get("end_date", ""), po.get("date", "")
    if cs and ce and pd:
        cell("period", "pass" if cs <= pd <= ce else "fail", f"po@{pd} vs [{cs},{ce}]")
    elif cs and ce:
        cell("period", "pass", "no po date to check")
    else:
        cell("period", "flag", "contract window open-ended")
    # 10 line count
    cell("line_count", "pass" if 0 < len(inv_lines) <= len(po_lines) else "fail", f"po={len(po_lines)} inv={len(inv_lines)}")
    # 11 duplicates
    cell("duplicates", "fail" if prior_invoice_count > 0 else "pass", f"prior={prior_invoice_count}")

    fails = [c for c in cells if c["status"] == "fail"]
    overall = "CLEAN" if not fails else "HOLD"
    hold_amount = 0 if not fails else abs(po_total - inv_total) or inv_total
    return {"cells": cells, "overall": overall, "hold_amount_minor": hold_amount, "hash": verdict_hash(cells)}
