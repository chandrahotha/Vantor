"""Sourcing service — lifecycle guards + deterministic totals (integer money).

- RFQ lifecycle: draft → sent → response → evaluated → awarded → closed.
- Quote: draft → submitted → evaluated → awarded|rejected. Only submitted+
  quotes can be evaluated/awarded. One quote per (rfq, supplier).
- Award: exactly one per RFQ; awarded_total_minor is server-computed from the
  winning quote's lines (never client-supplied). RFQ must be in evaluated.
- Totals: sum(line_total_minor); each line_total = unit_price * quantity.
  Negative/zero prices rejected (zero allowed only if quantity is 0? No —
  reject non-positive unit prices to keep spend analytics honest).
"""
from __future__ import annotations

from ..models.sourcing import QUOTE_STATUSES, RFQ_STATUSES

RFQ_FLOW = {
    "draft": {"sent"},
    "sent": {"response", "closed"},
    "response": {"evaluated", "closed"},
    "evaluated": {"awarded", "closed"},
    "awarded": {"closed"},
    "closed": set(),
}
QUOTE_FLOW = {
    "draft": {"submitted"},
    "submitted": {"evaluated", "rejected"},
    "evaluated": {"awarded", "rejected"},
    "awarded": set(),
    "rejected": set(),
}


class SourcingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def check_rfq_transition(old: str, new: str) -> None:
    if old not in RFQ_STATUSES or new not in RFQ_STATUSES:
        raise SourcingError("RFQ_STATUS_INVALID", f"unknown RFQ status {old!r}->{new!r}")
    if new not in RFQ_FLOW[old]:
        raise SourcingError("RFQ_LIFECYCLE_INVALID", f"RFQ cannot move {old}->{new}")


def check_quote_transition(old: str, new: str) -> None:
    if old not in QUOTE_STATUSES or new not in QUOTE_STATUSES:
        raise SourcingError("QUOTE_STATUS_INVALID", f"unknown quote status {old!r}->{new!r}")
    if new not in QUOTE_FLOW[old]:
        raise SourcingError("QUOTE_LIFECYCLE_INVALID", f"quote cannot move {old}->{new}")


def line_total(unit_price_minor: int, quantity: int) -> int:
    if not isinstance(unit_price_minor, int) or isinstance(unit_price_minor, bool) or unit_price_minor <= 0:
        raise SourcingError("QUOTE_PRICE_INVALID", "unit_price_minor must be a positive integer (minor units)")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise SourcingError("QUOTE_QTY_INVALID", "quantity must be a positive integer")
    total = unit_price_minor * quantity
    if total <= 0:
        raise SourcingError("QUOTE_TOTAL_INVALID", "line total overflow/invalid")
    return total
