"""Contract service — lifecycle + date/renewal rules (real calendar logic).

- Dates are ISO YYYY-MM-DD, validated real calendar dates (no 2026-02-30).
- end_date >= start_date when both present.
- Lifecycle: draft→review→active→{expiring→renewed|expired, terminated}.
  `expiring` may only be entered from active; renewal creates the renewed link
  via new contract (renewed_from) — here: status move active→renewed requires
  a successor code in notes? Keep simple: renewed allowed from expiring only.
- Expiry derivation: active contract with end_date within 90 days => due for
  expiring (server computes; endpoint POST /contracts/roll-expiry moves them
  in bulk with one audit row per contract).
"""
from __future__ import annotations

from datetime import date

from ..models.contract import CONTRACT_STATUSES, OBLIGATION_STATUSES

CONTRACT_FLOW = {
    "draft": {"review", "terminated"},
    "review": {"active", "terminated"},
    "active": {"expiring", "terminated", "expired"},
    "expiring": {"renewed", "expired", "terminated"},
    "renewed": set(),
    "expired": set(),
    "terminated": set(),
}
EXPIRY_WINDOW_DAYS = 90


class ContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_iso_day(raw: str, field: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        y, m, d = (int(p) for p in raw.split("-"))
        return date(y, m, d)  # raises on impossible dates — real calendar
    except Exception as exc:
        raise ContractError("CONTRACT_DATE_INVALID", f"{field} must be ISO YYYY-MM-DD, got {raw!r}") from exc


def check_dates(start: str, end: str) -> None:
    s, e = parse_iso_day(start, "start_date"), parse_iso_day(end, "end_date")
    if s and e and e < s:
        raise ContractError("CONTRACT_DATES_INVERTED", "end_date cannot precede start_date")


def check_transition(old: str, new: str) -> None:
    if old not in CONTRACT_STATUSES or new not in CONTRACT_STATUSES:
        raise ContractError("CONTRACT_STATUS_INVALID", f"unknown contract status {old!r}->{new!r}")
    if new not in CONTRACT_FLOW[old]:
        raise ContractError("CONTRACT_LIFECYCLE_INVALID", f"contract cannot move {old}->{new}")


def is_due_expiring(status: str, end: str, today: date) -> bool:
    if status != "active" or not end:
        return False
    e = parse_iso_day(end, "end_date")
    if e is None:
        return False
    delta = (e - today).days
    return 0 <= delta <= EXPIRY_WINDOW_DAYS


def check_obligation(status: str, due: str) -> None:
    if status not in OBLIGATION_STATUSES:
        raise ContractError("OBLIGATION_STATUS_INVALID", f"unknown obligation status {status!r}")
    parse_iso_day(due, "due_date")
