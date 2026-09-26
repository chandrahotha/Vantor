"""Supplier scoring engine — deterministic weighted KPIs (SupplierRadar pattern).

Dimensions (0..1000 permille each, weights sum to 1000):
  quality, delivery, price, compliance, responsiveness.
Score = Σ(dim × weight) // 1000 (integer floor — conservative by design).
Grade bands: A ≥850, B ≥700, C ≥550, D ≥400, else F.
Risk tier derives from score + hard flags (blocked certs, critical non-compliance):
  score ≥700 → low; ≥550 → medium; else high; any hard flag → critical.

All inputs validated; unknown dimensions rejected (never defaulted to average).
Golden vectors in tests/test_scoring.py.
"""
from __future__ import annotations

DIMS = ("quality", "delivery", "price", "compliance", "responsiveness")
GRADES = ((850, "A"), (700, "B"), (550, "C"), (400, "D"), (0, "F"))


class ScoringError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _permille(v: int, field: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 1000:
        raise ScoringError("SCORE_RANGE_INVALID", f"{field} must be integer 0..1000")
    return v


def score(*, dims: dict, weights: dict, hard_flags: int = 0) -> dict:
    if set(dims) != set(DIMS):
        raise ScoringError("SCORE_DIMS_INVALID", f"dims must be exactly {sorted(DIMS)}")
    if set(weights) != set(DIMS):
        raise ScoringError("SCORE_WEIGHTS_INVALID", f"weights must be exactly {sorted(DIMS)}")
    if sum(weights.values()) != 1000:
        raise ScoringError("SCORE_WEIGHTS_SUM", "weights must sum to 1000 permille")
    vals = {k: _permille(v, f"dim.{k}") for k, v in dims.items()}
    wts = {k: _permille(v, f"weight.{k}") for k, v in weights.items()}
    total = sum(vals[k] * wts[k] for k in DIMS) // 1000
    grade = next(g for bound, g in GRADES if total >= bound)
    if hard_flags:
        tier = "critical"
    elif total >= 700:
        tier = "low"
    elif total >= 550:
        tier = "medium"
    else:
        tier = "high"
    return {"score": total, "grade": grade, "risk_tier": tier, "dims": vals}


DEFAULT_WEIGHTS = {"quality": 300, "delivery": 250, "price": 200, "compliance": 150, "responsiveness": 100}
