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


def evaluate(*, contract: dict, po: dict, invoice: dict,
             prior_invoice_lines: list[dict] | None = None,
             po_line_quantities: dict[str, int] | None = None) -> dict:
    """All amounts integer minor units. Returns {cells, overall, hold_amount_minor, hash}.

    `prior_invoice_lines` are the `(po_line_id, quantity, unit_price_minor)`
    triples of every *other* invoice already recorded against this PO, and
    `po_line_quantities` the ordered quantity per PO line id. Together they let
    the `duplicates` dimension answer the question it is named for — "is this
    bill paying for the same thing twice?" — instead of the much cruder "has any
    other invoice ever existed?".

    That distinction matters: partial invoicing is normal procurement, and the
    old check failed the second invoice of every partially-paid PO, holding
    legitimate money for ever.
    """
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
    # 5 totals — the invoice may not claim more than was ordered. It is explicitly
    # NOT required to equal the PO total: a partial invoice legitimately bills
    # less, and demanding equality held every partial payment for ever (and made
    # the `duplicates` fix above pointless on its own). Over-billing is still a
    # hard fail; under-billing is ordinary procurement.
    if inv_total > 0 and inv_total <= po_total:
        cell("totals", "pass", f"po={po_total} inv={inv_total} (partial ok)")
    elif inv_total <= 0:
        cell("totals", "fail", f"po={po_total} inv={inv_total} empty invoice total")
    else:
        cell("totals", "fail", f"invoice total {inv_total} exceeds PO total {po_total}")

    # 6 quantities + 7 prices — pair invoice lines to PO lines by id, not by
    # position. Index pairing compared the wrong lines whenever an invoice listed
    # its lines in a different order than the PO, which is a supplier's choice.
    def _pairs(po_l: list[dict], inv_l: list[dict]) -> list[tuple[dict, dict]] | None:
        if not po_l or not inv_l or len(inv_l) > len(po_l):
            return None
        po_by_id = {str(l.get("po_line_id", "")): l for l in po_l if l.get("po_line_id")}
        if len(po_by_id) == len(po_l) and all(il.get("po_line_id") in po_by_id for il in inv_l):
            return [(po_by_id[str(il["po_line_id"])], il) for il in inv_l]
        return [(po_l[i], il) for i, il in enumerate(inv_l)]

    pairs = _pairs(po_lines, inv_lines)
    if pairs is None:
        cell("quantities", "fail", "invoice lines do not map onto PO lines")
        cell("prices", "fail", "invoice lines do not map onto PO lines")
    else:
        bad_qty = [str(p.get("po_line_id", i)) for i, (p, il) in enumerate(pairs)
                   if il.get("quantity", 0) > p.get("quantity", -1)]
        cell("quantities", "fail" if bad_qty else "pass",
             "" if not bad_qty else f"invoiced qty exceeds ordered on {', '.join(bad_qty)}")
        bad_price = [str(p.get("po_line_id", i)) for i, (p, il) in enumerate(pairs)
                     if il.get("unit_price_minor") != p.get("unit_price_minor")]
        cell("prices", "fail" if bad_price else "pass",
             "" if not bad_price else f"unit price drift vs PO on {', '.join(bad_price)}")
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
    # 11 duplicates — real double-billing, not "another invoice exists".
    # Fail only when this invoice pushes cumulative invoiced quantity past what
    # was ordered, or re-bills a (po_line, qty, price) triple another invoice
    # already paid for. Partial invoicing must stay CLEAN.
    prior_lines = prior_invoice_lines or []
    ordered = po_line_quantities or {}
    prior_by_line: dict[str, int] = {}
    prior_triples: set[tuple] = set()
    for pl in prior_lines:
        line_id = str(pl.get("po_line_id", ""))
        qty = int(pl.get("quantity", 0) or 0)
        prior_by_line[line_id] = prior_by_line.get(line_id, 0) + qty
        prior_triples.add((line_id, qty, int(pl.get("unit_price_minor", 0) or 0)))
    over_ordered: list[str] = []
    repeated: list[str] = []
    for il in invoice.get("lines", []):
        line_id = str(il.get("po_line_id", ""))
        qty = int(il.get("quantity", 0) or 0)
        if line_id in ordered and prior_by_line.get(line_id, 0) + qty > ordered[line_id]:
            over_ordered.append(line_id)
        if (line_id, qty, int(il.get("unit_price_minor", 0) or 0)) in prior_triples:
            repeated.append(line_id)
    if over_ordered:
        cell("duplicates", "fail", f"invoiced beyond ordered on po line(s) {', '.join(sorted(set(over_ordered)))}")
    elif repeated:
        cell("duplicates", "fail", f"identical line already invoiced: {', '.join(sorted(set(repeated)))}")
    elif prior_lines:
        cell("duplicates", "pass", f"partial invoicing within ordered quantity ({len(prior_lines)} prior line(s))")
    else:
        cell("duplicates", "pass", "no prior invoices on this PO")

    fails = [c for c in cells if c["status"] == "fail"]
    overall = "CLEAN" if not fails else "HOLD"
    hold_amount = 0 if not fails else abs(po_total - inv_total) or inv_total
    return {"cells": cells, "overall": overall, "hold_amount_minor": hold_amount, "hash": verdict_hash(cells)}
