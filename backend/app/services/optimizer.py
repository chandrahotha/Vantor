"""Sourcing optimizer — 06 (spec 06_STRATEGICSOURCE): explainable allocations.

Given evaluated quotes for an RFQ + policy constraints, produce the cheapest
feasible allocation. Deterministic greedy: cheapest-first up to each supplier's
max share; every pick carries its reason. Constraints:
- max_share_bp: no supplier takes more than this share (diversification policy).
- exclude: supplier ids barred from this award (policy/risk).
- min_quotes: refuse to optimize with fewer (no thin evidence).
Outputs: allocations [{supplier, share_bp, cost_minor, reason}], total, violations.
All money integer minor; shares integer bp summing to exactly 10000.
"""
from __future__ import annotations


class OptimizerError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def allocate(*, quotes: list[dict], max_share_bp: int = 10_000,
             exclude: set[str] | None = None, min_quotes: int = 2) -> dict:
    exclude = exclude or set()
    if not 1 <= max_share_bp <= 10_000:
        raise OptimizerError("OPT_SHARE_INVALID", "max_share_bp must be 1..10000")
    pool = [q for q in quotes if q["supplier_id"] not in exclude and q["total_minor"] > 0]
    if len(pool) < min_quotes:
        raise OptimizerError("OPT_THIN_FIELD", f"only {len(pool)} eligible quotes (< {min_quotes})")
    pool.sort(key=lambda q: q["total_minor"])
    remaining = 10_000
    allocs: list[dict] = []
    violations: list[str] = []
    for i, q in enumerate(pool):
        if remaining <= 0:
            break
        last = i == len(pool) - 1
        if last and remaining > max_share_bp:
            share = remaining
            violations.append(f"{q['supplier_id']} takes {share}bp over {max_share_bp}bp cap — field too tight to diversify")
            reason = "only eligible supplier left (over cap, flagged)"
        else:
            share = min(max_share_bp, remaining)
            reason = "cheapest eligible" if i == 0 else f"next cheapest within {max_share_bp}bp cap"
        # Allocated cost = this supplier's quoted total pro-rated by share.
        cost = q["total_minor"] * share // 10_000
        allocs.append({"supplier_id": q["supplier_id"], "quote_id": q["quote_id"], "share_bp": share,
                       "cost_minor": cost, "reason": reason})
        remaining -= share
    if remaining > 0:
        raise OptimizerError("OPT_INFEASIBLE", f"caps too tight: {remaining}bp unallocated")
    return {"allocations": allocs, "total_minor": sum(a["cost_minor"] for a in allocs),
            "share_sum_bp": sum(a["share_bp"] for a in allocs), "violations": violations}
