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
             po_line_quantities: dict[str, int] | None = None,
             received_quantities: dict[str, int] | None = None,
             prior_approved_quantities: dict[str, int] | None = None) -> dict:
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

    `received_quantities` and `prior_approved_quantities` are what make this the
    *three*-way match rather than a two-way one. They are the cumulative
    goods-received and the cumulative already-approved-invoice quantity per PO
    line, both excluding the invoice under evaluation. The `quantities`
    dimension then enforces the real procurement invariant:

        approved_prior_qty + current_qty <= received_qty <= ordered_qty

    Both are optional so the advisory `/contracts/{id}/match` endpoint can run
    without receipts. The money path (`services.purchase.three_way_match`) always
    supplies both — which is the point: there is one engine, and the approval
    path cannot accidentally use the weaker form.
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
    # A *mismatch* is a hard fail. An *unspecified* currency is missing data, not
    # a disagreement, so it is a flag a human sees rather than a hold. The old
    # form (`... and po.get("currency")`) failed every document that simply had
    # not been given a currency, which meant routing the money path through this
    # engine started holding invoices that were in fact fine.
    _currencies = {contract.get("currency") or "", po.get("currency") or "", invoice.get("currency") or ""}
    if not _currencies - {""}:
        cell("currency", "pass", "not specified on any document")
    elif len(_currencies) == 1:
        cell("currency", "pass")
    else:
        cell("currency", "fail", f"currency mismatch across documents: {sorted(_currencies)}")
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
    # The cumulative three-way quantities, resolved once. `prior_approved` is what
    # earlier invoices have already been approved for; `received` is what goods
    # have actually come in. VNT-001: only the *current* invoice's quantity was
    # ever compared against `received`, so 60 + 60 invoiced against 100 received
    # passed — the same goods billed twice, and two `actual` ledger rows for it.
    received = received_quantities or {}
    prior_approved = prior_approved_quantities or {}
    if pairs is None:
        cell("quantities", "fail", "invoice lines do not map onto PO lines")
        cell("prices", "fail", "invoice lines do not map onto PO lines")
    else:
        bad_qty: list[str] = []
        for p, il in pairs:
            line_id = str(p.get("po_line_id", ""))
            qty = int(il.get("quantity", 0) or 0)
            ordered_qty = p.get("quantity", -1)
            why: list[str] = []
            if qty > ordered_qty:
                why.append(f"invoiced {qty} > ordered {ordered_qty}")
            # Over-receipt means the goods themselves were recorded against the
            # PO beyond what was ordered, which invalidates every invoice against
            # it. Caught here as well as at the receipt, because a bad receipt
            # written before this check existed must not be silently honoured.
            recv = received.get(line_id)
            if recv is not None and recv > ordered_qty:
                why.append(f"received {recv} > ordered {ordered_qty}")
            # The load-bearing one: cumulative approved + current <= received.
            if recv is not None:
                approved_so_far = int(prior_approved.get(line_id, 0) or 0)
                if approved_so_far + qty > recv:
                    why.append(f"cumulative invoiced {approved_so_far}+{qty} > received {recv}")
            if why:
                bad_qty.append(f"{line_id}: " + "; ".join(why))
        cell("quantities", "fail" if bad_qty else "pass",
             "" if not bad_qty else " | ".join(bad_qty))
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
    # The hard fail is cumulative quantity past what was ordered; the
    # cumulative-received invariant itself lives in `quantities`, which is the
    # dimension that has the receipts. An identical `(line, qty, price)` triple
    # repeating is a *flag*, not a fail: two separate deliveries of 10 bolts at
    # the same price produce exactly that pair of lines and are perfectly
    # legitimate, so failing it would hold real money for ever over a shape the
    # data cannot distinguish from fraud.
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
        cell("duplicates", "flag",
             f"line/qty/price repeats an earlier invoice on {', '.join(sorted(set(repeated)))} — "
             f"verify these are separate deliveries, not a re-bill")
    elif prior_lines:
        cell("duplicates", "pass", f"partial invoicing within ordered quantity ({len(prior_lines)} prior line(s))")
    else:
        cell("duplicates", "pass", "no prior invoices on this PO")

    fails = [c for c in cells if c["status"] == "fail"]
    overall = "CLEAN" if not fails else "HOLD"
    hold_amount = 0 if not fails else abs(po_total - inv_total) or inv_total
    return {"cells": cells, "overall": overall, "hold_amount_minor": hold_amount, "hash": verdict_hash(cells)}
