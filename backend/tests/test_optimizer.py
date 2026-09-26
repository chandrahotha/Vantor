"""Optimizer tests — cheapest-first splits, caps, exclusions, thin-field refusal."""
import pytest

from app.services.optimizer import allocate


def _q(sid, total):
    return {"supplier_id": sid, "quote_id": f"q-{sid}", "total_minor": total}


def test_single_winner_full_share():
    out = allocate(quotes=[_q("a", 100), _q("b", 200)])
    assert out["allocations"][0] == {"supplier_id": "a", "quote_id": "q-a", "share_bp": 10_000,
                                     "cost_minor": 100, "reason": "cheapest eligible"}
    assert out["share_sum_bp"] == 10_000 and out["violations"] == []


def test_cap_splits_60_40():
    out = allocate(quotes=[_q("a", 100), _q("b", 120)], max_share_bp=6000)
    assert [(a["supplier_id"], a["share_bp"]) for a in out["allocations"]] == [("a", 6000), ("b", 4000)]
    assert out["total_minor"] == 100 * 6000 // 10_000 + 120 * 4000 // 10_000 == 108
    assert out["share_sum_bp"] == 10_000


def test_exclude_and_violation():
    out = allocate(quotes=[_q("a", 100), _q("b", 120)], max_share_bp=6000, exclude={"a"}, min_quotes=1)
    assert len(out["allocations"]) == 1 and out["allocations"][0]["supplier_id"] == "b"
    assert out["violations"] != []  # 10000bp on one head over the 6000 cap, flagged


def test_thin_field_and_bad_cap():
    with pytest.raises(Exception):
        allocate(quotes=[_q("a", 100)])
    with pytest.raises(Exception):
        allocate(quotes=[_q("a", 100), _q("b", 120)], max_share_bp=0)
    with pytest.raises(Exception):
        allocate(quotes=[_q("a", 0), _q("b", 0)])
