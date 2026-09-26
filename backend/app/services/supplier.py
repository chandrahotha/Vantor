"""Supplier service — validation, normalization, dedupe (no synthetics).

Rules (production):
- code: 2–32 chars A-Z0-9_-, uppercased, trimmed. Unique per tenant (DB constraint).
- name: 2–300 chars, trimmed, no empty.
- status: lifecycle draft→active→on_hold→blocked→archived; no skipping out of archived.
- currency: ISO 4217 3-letter or empty; country: ISO 3166-1 alpha-2 or empty.
- Dedupe: exact code handled by DB; fuzzy name+country matches return a
  `possible_duplicate_of` hint (never auto-merge — buyer confirms).
"""
from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.supplier import SUPPLIER_STATUSES, Supplier

_CODE_RE = re.compile(r"^[A-Z0-9_-]{2,32}$")
_ISO_CCY = {
    "USD", "EUR", "GBP", "INR", "JPY", "CHF", "CAD", "AUD", "SEK", "NOK", "DKK",
    "PLN", "CZK", "HUF", "CNY", "SGD", "MXN", "BRL", "ZAR", "AED", "SAR",
}
_ARCHIVED_FROM = {"draft", "active", "on_hold", "blocked"}


class SupplierError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_code(raw: str) -> str:
    code = (raw or "").strip().upper()
    if not _CODE_RE.match(code):
        raise SupplierError("SUPPLIER_CODE_INVALID", "code must be 2-32 chars A-Z 0-9 _ -")
    return code


def validate_payload(name: str, status: str, currency: str, country: str) -> tuple[str, str, str, str]:
    name = (name or "").strip()
    if not 2 <= len(name) <= 300:
        raise SupplierError("SUPPLIER_NAME_INVALID", "name must be 2-300 chars")
    status = (status or "draft").strip()
    if status not in SUPPLIER_STATUSES:
        raise SupplierError("SUPPLIER_STATUS_INVALID", f"status must be one of {sorted(SUPPLIER_STATUSES)}")
    currency = (currency or "").strip().upper()
    if currency and currency not in _ISO_CCY:
        raise SupplierError("SUPPLIER_CURRENCY_UNKNOWN", f"Unknown currency {currency!r}")
    country = (country or "").strip().upper()
    if country and (len(country) != 2 or not country.isalpha()):
        raise SupplierError("SUPPLIER_COUNTRY_INVALID", "country must be ISO alpha-2 or empty")
    return name, status, currency, country


def check_lifecycle(old: str, new: str) -> None:
    if old == "archived" and new != "archived":
        raise SupplierError("SUPPLIER_LIFECYCLE_INVALID", "archived suppliers cannot be reactivated via update (restore flow only)")
    if new not in SUPPLIER_STATUSES:
        raise SupplierError("SUPPLIER_STATUS_INVALID", "unknown status")


def find_possible_duplicate(db: Session, *, tenant_id: str, name: str, country: str, exclude_id: str = "") -> str:
    """Return supplier id of a same-name+country row, else ''. Never auto-merges."""
    stmt = (
        select(Supplier.id)
        .where(Supplier.tenant_id == tenant_id)
        .where(func.lower(Supplier.name) == name.lower())
        .where(Supplier.country == country)
        .limit(2)
    )
    for (sid,) in db.execute(stmt):
        if sid != exclude_id:
            return sid
    return ""
