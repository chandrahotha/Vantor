"""Scoring golden vectors — conservative floor math, grade bands, risk tiers."""
import pytest

from app.services.scoring import DEFAULT_WEIGHTS, score


def test_perfect_and_zero():
    dims = {k: 1000 for k in ("quality", "delivery", "price", "compliance", "responsiveness")}
    r = score(dims=dims, weights=dict(DEFAULT_WEIGHTS))
    assert (r["score"], r["grade"], r["risk_tier"]) == (1000, "A", "low")
    r0 = score(dims={k: 0 for k in dims}, weights=dict(DEFAULT_WEIGHTS))
    assert (r0["score"], r0["grade"], r0["risk_tier"]) == (0, "F", "high")


def test_weighted_floor_and_bands():
    # only quality=1000 @300 weight => 300 -> F (floor, never rounds up into D)
    dims = {"quality": 1000, "delivery": 0, "price": 0, "compliance": 0, "responsiveness": 0}
    r = score(dims=dims, weights=dict(DEFAULT_WEIGHTS))
    assert r["score"] == 300 and r["grade"] == "F"
    # uniform 700 => 700 => B/low boundary
    r2 = score(dims={k: 700 for k in dims}, weights=dict(DEFAULT_WEIGHTS))
    assert (r2["score"], r2["grade"], r2["risk_tier"]) == (700, "B", "low")
    # uniform 549 => C? 549 < 550 => D... check band edge precisely
    r3 = score(dims={k: 549 for k in dims}, weights=dict(DEFAULT_WEIGHTS))
    assert (r3["score"], r3["grade"]) == (549, "D")
    # hard flag forces critical regardless of score
    r4 = score(dims={k: 1000 for k in dims}, weights=dict(DEFAULT_WEIGHTS), hard_flags=1)
    assert r4["risk_tier"] == "critical"


def test_rejects_guesses():
    with pytest.raises(Exception):
        score(dims={"quality": 100}, weights=dict(DEFAULT_WEIGHTS))  # missing dims
    with pytest.raises(Exception):
        score(dims={k: 500 for k in DEFAULT_WEIGHTS}, weights={"quality": 1000})  # missing weights
    with pytest.raises(Exception):
        score(dims={k: 500 for k in DEFAULT_WEIGHTS}, weights={k: 200 for k in DEFAULT_WEIGHTS} | {"quality": 201})  # sum != 1000
    with pytest.raises(Exception):
        score(dims={k: 1500 for k in DEFAULT_WEIGHTS}, weights=dict(DEFAULT_WEIGHTS))  # out of range


def test_api_roundtrip():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app, raise_server_exceptions=False)
    assert c.post("/api/v1/suppliers/x/scorecard", json={"dims": {}}).status_code == 401
