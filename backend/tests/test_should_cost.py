"""Should-cost golden vectors — bit-exact integer math, half-up rounding."""
from app.services.should_cost import gap_vs_quote, model_total


def test_rollup_golden():
    # material 10000.00 + labor 2500.00, overhead 15% (1500bp), logistics 500.00, margin 10% (1000bp)
    b = model_total(material_minor=1_000_000, labor_minor=250_000, overhead_bp=1500, logistics_minor=50_000, margin_bp=1000)
    assert b["prime_minor"] == 1_250_000
    assert b["overhead_minor"] == 187_500  # 1250000 * 0.15 exact
    assert b["subtotal_minor"] == 1_487_500
    assert b["margin_minor"] == 148_750
    assert b["should_minor"] == 1_636_250


def test_half_up_rounding():
    # 1 minor @ 50% (5000bp) => 0.5 rounds up to 1
    b = model_total(material_minor=1, labor_minor=0, overhead_bp=5000, logistics_minor=0, margin_bp=0)
    assert b["overhead_minor"] == 1
    assert b["should_minor"] == 2


def test_zero_model():
    b = model_total(material_minor=0, labor_minor=0, overhead_bp=0, logistics_minor=0, margin_bp=0)
    assert b["should_minor"] == 0


def test_gap_vectors():
    g = gap_vs_quote(should_minor=1_636_250, quoted_minor=1_800_000)
    assert g["gap_minor"] == 163_750 and g["verdict"] == "above"
    assert g["variance_bp"] == round(163_750 / 1_636_250 * 10_000)
    g2 = gap_vs_quote(should_minor=1_636_250, quoted_minor=1_500_000)
    assert g2["verdict"] == "below"
    g3 = gap_vs_quote(should_minor=1_636_250, quoted_minor=1_636_250)
    assert g3["verdict"] == "at_par" and g3["gap_minor"] == 0
    assert gap_vs_quote(should_minor=0, quoted_minor=100)["variance_bp"] == 0


def test_rejects_guesses():
    import pytest as _pt

    with _pt.raises(Exception):
        model_total(material_minor=-1, labor_minor=0, overhead_bp=0, logistics_minor=0, margin_bp=0)
    with _pt.raises(Exception):
        model_total(material_minor=100, labor_minor=0, overhead_bp=10001, logistics_minor=0, margin_bp=0)
    with _pt.raises(Exception):
        gap_vs_quote(should_minor=100, quoted_minor=1.5)


def test_api_endpoint_shape():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app, raise_server_exceptions=False)
    # unauthenticated => 401 envelope (route exists and is gated)
    r = c.post("/api/v1/spend/should-cost", json={"material_minor": 100, "labor_minor": 0, "overhead_bp": 0, "logistics_minor": 0, "margin_bp": 0})
    assert r.status_code == 401
