"""Should-cost engine — deterministic integer-minor money math (CostPilot pattern).

A should-cost model breaks a part price into cost elements and rolls them up:
  material + process(labor) + overhead + logistics + margin = should-cost.
All money is integer minor units; percentages are integer basis points
(1% = 100bp) so every machine computes bit-identical results. No floats, no
guessing: unknown elements are rejected, never defaulted.

Golden vectors live in tests/test_should_cost.py — any change must keep them green.
"""
from __future__ import annotations

BP = 10_000  # basis points per 100%


class ShouldCostError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _minor(v: int, field: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise ShouldCostError("COST_MONEY_INVALID", f"{field} must be a non-negative integer (minor units)")
    return v


def _bp(v: int, field: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 100 * 100:
        raise ShouldCostError("COST_PCT_INVALID", f"{field} must be integer basis points 0..10000")
    return v


def pct_of(base_minor: int, bp: int) -> int:
    """Half-up integer percent: (base * bp + BP//2) // BP."""
    return (base_minor * bp + BP // 2) // BP


def model_total(*, material_minor: int, labor_minor: int, overhead_bp: int, logistics_minor: int, margin_bp: int) -> dict:
    """Roll up one unit should-cost. Returns the full deterministic breakdown."""
    mat, lab, log = _minor(material_minor, "material_minor"), _minor(labor_minor, "labor_minor"), _minor(logistics_minor, "logistics_minor")
    oh_bp, mg_bp = _bp(overhead_bp, "overhead_bp"), _bp(margin_bp, "margin_bp")
    prime = mat + lab
    overhead = pct_of(prime, oh_bp)
    subtotal = prime + overhead + log
    margin = pct_of(subtotal, mg_bp)
    return {"material_minor": mat, "labor_minor": lab, "prime_minor": prime, "overhead_minor": overhead,
            "logistics_minor": log, "subtotal_minor": subtotal, "margin_minor": margin,
            "should_minor": subtotal + margin}


def gap_vs_quote(*, should_minor: int, quoted_minor: int) -> dict:
    """Signed gap (quote − should) + variance in basis points vs should."""
    should_minor = _minor(should_minor, "should_minor")
    quoted_minor = _minor(quoted_minor, "quoted_minor")
    gap = quoted_minor - should_minor
    variance_bp = round(gap / should_minor * BP) if should_minor else 0
    return {"gap_minor": gap, "variance_bp": variance_bp,
            "verdict": "above" if gap > 0 else "below" if gap < 0 else "at_par"}
