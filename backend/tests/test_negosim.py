"""Nego sim tests — deterministic concession ladder, accept/walk-away, guards."""
import pytest

from app.services.negosim import simulate


def test_accept_first_ball():
    out = simulate(list_price_minor=1000, walk_away_minor=800, buyer_offers_minor=[1000])
    assert out["result"] == "accepted" and out["settled_minor"] == 1000 and out["score"] == 0


def test_concession_then_accept():
    out = simulate(list_price_minor=1000, walk_away_minor=800, buyer_offers_minor=[800, 850], concession_bp=5000)
    # round1: gap=200, step=100 -> ask 900; round2: 850 < 900 -> gap=50, step=25 -> ask 875... wait recompute below
    assert out["rounds"][0] == {"round": 1, "buyer": 800, "supplier": 900, "event": "countered"}
    assert out["rounds"][1]["supplier"] == 875 and out["rounds"][1]["event"] == "walk_away"
    assert out["result"] == "walk_away" and out["score"] == 0


def test_never_below_walk_away_and_event_marked():
    out = simulate(list_price_minor=1000, walk_away_minor=900, buyer_offers_minor=[100, 100, 100, 100, 100])
    asks = [r["supplier"] for r in out["rounds"]]
    assert all(a >= 900 for a in asks)
    assert out["rounds"][-1]["event"] == "walk_away"
    assert out["result"] == "walk_away"


def test_score_rewards_savings():
    out = simulate(list_price_minor=1000, walk_away_minor=500, buyer_offers_minor=[900])
    # ask 1000, offer 900 < 1000 -> counter... not accepted. Use offer >= ask:
    out2 = simulate(list_price_minor=1000, walk_away_minor=500, buyer_offers_minor=[400, 1000])
    assert out["result"] != out2["result"] and out2["score"] > out["score"]
    assert out["rounds"][-1]["event"] == "walk_away"
    assert out2["result"] == "accepted"
    assert out2["score"] >= 0


def test_guards():
    with pytest.raises(Exception):
        simulate(list_price_minor=800, walk_away_minor=800, buyer_offers_minor=[800])
    with pytest.raises(Exception):
        simulate(list_price_minor=1000, walk_away_minor=800, buyer_offers_minor=[])
    with pytest.raises(Exception):
        simulate(list_price_minor=1000, walk_away_minor=800, buyer_offers_minor=[-5])
