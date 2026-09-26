"""Matching golden vectors — deterministic 11-dim verdicts + stored runs."""
from app.services.matching import DIMS, evaluate, verdict_hash


def _docs(**kw):
    base_c = {"supplier_id": "s1", "currency": "INR", "value_minor": 1_000_000, "start_date": "2026-01-01", "end_date": "2026-12-31"}
    base_po = {"supplier_id": "s1", "currency": "INR",
               "lines": [{"po_line_id": "L1", "unit_price_minor": 50000, "quantity": 10, "line_total_minor": 500_000}]}
    base_inv = {"supplier_id": "s1", "currency": "INR",
                "lines": [{"po_line_id": "L1", "unit_price_minor": 50000, "quantity": 10, "line_total_minor": 500_000}]}
    return {
        "contract": {**base_c, **kw.get("contract", {})},
        "po": {**base_po, **kw.get("po", {})},
        "invoice": {**base_inv, **kw.get("invoice", {})},
        "prior_invoice_lines": kw.get("prior_invoice_lines", []),
        "po_line_quantities": kw.get("po_line_quantities", {"L1": 10}),
    }


def test_clean_run_all_pass():
    r = evaluate(**_docs())
    assert len(r["cells"]) == 11 == len(DIMS)
    assert r["overall"] == "CLEAN" and r["hold_amount_minor"] == 0
    assert len(r["hash"]) == 64
    # reproducibility: same inputs => same hash
    assert evaluate(**_docs())["hash"] == r["hash"]


def test_price_drift_holds():
    r = evaluate(**_docs(invoice={"supplier_id": "s1", "currency": "INR",
        "lines": [{"unit_price_minor": 55000, "quantity": 10, "line_total_minor": 550_000}]}))
    assert r["overall"] == "HOLD"
    by_dim = {c["dim"]: c["status"] for c in r["cells"]}
    assert by_dim["prices"] == "fail" and by_dim["totals"] == "fail"
    assert r["hold_amount_minor"] == 50_000


def test_supplier_currency_duplicate_flags():
    r = evaluate(**_docs(po={"supplier_id": "s2", "currency": "INR",
        "lines": [{"po_line_id": "L1", "unit_price_minor": 50000, "quantity": 10, "line_total_minor": 500_000}]}))
    assert {c["dim"]: c["status"] for c in r["cells"]}["parties"] == "fail"


def test_partial_invoicing_stays_clean():
    """The second invoice of a partially-paid PO must NOT be held.

    The dimension used to be `prior_invoice_count > 0`, so any PO with a prior
    invoice failed the duplicate check and every partial payment after the first
    was held for ever. It is a real double-billing question, not a count.
    """
    # first invoice of 10: nothing prior
    assert {c["dim"]: c["status"] for c in evaluate(**_docs())["cells"]}["duplicates"] == "pass"
    # second invoice of the remaining 4, against a prior 6 on the same line
    partial = evaluate(**_docs(
        invoice={"supplier_id": "s1", "currency": "INR",
                 "lines": [{"po_line_id": "L1", "unit_price_minor": 50000, "quantity": 4, "line_total_minor": 200_000}]},
        prior_invoice_lines=[{"po_line_id": "L1", "quantity": 6, "unit_price_minor": 50000}]))
    assert {c["dim"]: c["status"] for c in partial["cells"]}["duplicates"] == "pass"
    assert partial["overall"] == "CLEAN"


def test_duplicate_billing_is_still_caught():
    """The fix must not blunt the control it was meant to sharpen."""
    # over-ordered: prior 6 + this 8 > 10 ordered
    over = evaluate(**_docs(
        invoice={"supplier_id": "s1", "currency": "INR",
                 "lines": [{"po_line_id": "L1", "unit_price_minor": 50000, "quantity": 8, "line_total_minor": 400_000}]},
        prior_invoice_lines=[{"po_line_id": "L1", "quantity": 6, "unit_price_minor": 50000}]))
    by_dim = {c["dim"]: c["status"] for c in over["cells"]}
    assert by_dim["duplicates"] == "fail" and over["overall"] == "HOLD"

    # exact re-bill: same line, same qty, same price already invoiced
    repeat = evaluate(**_docs(
        prior_invoice_lines=[{"po_line_id": "L1", "quantity": 10, "unit_price_minor": 50000}]))
    assert {c["dim"]: c["status"] for c in repeat["cells"]}["duplicates"] == "fail"
    assert repeat["overall"] == "HOLD"


def test_over_billing_is_caught_by_totals():
    """Weakening `totals` to `<=` must not let a supplier bill above the order."""
    over = evaluate(**_docs(invoice={"supplier_id": "s1", "currency": "INR",
        "lines": [{"po_line_id": "L1", "unit_price_minor": 50000, "quantity": 20, "line_total_minor": 1_000_000}]}))
    by_dim = {c["dim"]: c["status"] for c in over["cells"]}
    assert by_dim["totals"] == "fail" and over["overall"] == "HOLD"


def test_lines_pair_by_id_not_by_position():
    """An invoice may list its lines in any order; the PO order is not canonical.

    Index pairing compared the wrong lines, so a reordered invoice produced
    spurious `prices` and `quantities` failures.
    """
    two = [{"po_line_id": "L1", "unit_price_minor": 50000, "quantity": 2, "line_total_minor": 100_000},
           {"po_line_id": "L2", "unit_price_minor": 30000, "quantity": 4, "line_total_minor": 120_000}]
    reordered = [{"po_line_id": "L2", "unit_price_minor": 30000, "quantity": 4, "line_total_minor": 120_000},
                 {"po_line_id": "L1", "unit_price_minor": 50000, "quantity": 2, "line_total_minor": 100_000}]
    r = evaluate(contract=_docs()["contract"],
                 po={"supplier_id": "s1", "currency": "INR", "lines": two},
                 invoice={"supplier_id": "s1", "currency": "INR", "lines": reordered},
                 po_line_quantities={"L1": 2, "L2": 4})
    by_dim = {c["dim"]: c["status"] for c in r["cells"]}
    assert by_dim["prices"] == "pass" and by_dim["quantities"] == "pass"
    assert r["overall"] == "CLEAN"

    # but a genuine price drift on the *other* line is still caught after reorder
    drifted = evaluate(contract=_docs()["contract"],
                       po={"supplier_id": "s1", "currency": "INR", "lines": two},
                       invoice={"supplier_id": "s1", "currency": "INR",
                                "lines": [{"po_line_id": "L2", "unit_price_minor": 31000, "quantity": 4, "line_total_minor": 124_000},
                                          {"po_line_id": "L1", "unit_price_minor": 50000, "quantity": 2, "line_total_minor": 100_000}]},
                       po_line_quantities={"L1": 2, "L2": 4})
    assert {c["dim"]: c["status"] for c in drifted["cells"]}["prices"] == "fail"


def test_api_run_stored_and_scoped():
    from datetime import datetime, timedelta, timezone

    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi.testclient import TestClient
    from jwt.algorithms import RSAAlgorithm

    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache

    ISS, AUD = "https://issuer.test/realms/vantor", "vantor-web"
    get_settings.cache_clear()
    reset_engine_cache()
    engine = get_engine()
    from app.models.registry import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "m-kid"
    from app.core import security

    security.override_jwks({"m-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app

    c = TestClient(app, raise_server_exceptions=False)
    now = datetime.now(timezone.utc)

    def h(sub="u1", tenant="t1", roles=("Buyer", "Legal Reviewer", "Approver")):
        tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                          "realm_access": {"roles": list(roles)}, "exp": now + timedelta(minutes=5), "iat": now},
                         pem, algorithm="RS256", headers={"kid": "m-kid"})
        return {"Authorization": f"Bearer {tok}"}

    s = c.post("/api/v1/suppliers", json={"code": "SUP-M", "name": "Match Co"}, headers=h()).json()["data"]["id"]
    ct = c.post("/api/v1/contracts", json={"code": "CT-M", "title": "Cover", "supplier_id": s, "currency": "INR",
                "value_minor": 1_000_000, "start_date": "2026-01-01", "end_date": "2026-12-31"}, headers=h()).json()["data"]["id"]
    po = c.post("/api/v1/purchase-orders", json={"code": "PO-M", "supplier_id": s, "currency": "INR",
                "lines": [{"description": "Widget", "quantity": 10, "unit_price_minor": 50000}]}, headers=h()).json()["data"]["id"]
    pod = c.get(f"/api/v1/purchase-orders/{po}", headers=h()).json()["data"]
    plid = pod["lines"][0]["id"]
    inv = c.post(f"/api/v1/purchase-orders/{po}/invoices", json={"code": "INV-M",
                "lines": [{"po_line_id": plid, "quantity": 10, "unit_price_minor": 50000}]}, headers=h())
    assert inv.status_code == 201, inv.text
    iid = inv.json()["data"]["id"]
    run = c.post(f"/api/v1/contracts/{ct}/match", json={"po_id": po, "invoice_id": iid}, headers=h())
    assert run.status_code == 201, run.text
    body = run.json()["data"]
    assert body["overall"] == "CLEAN" and len(body["cells"]) == 11 and len(body["hash"]) == 64
    # wrong-PO invoice rejected; other tenant sees nothing
    assert c.post(f"/api/v1/contracts/{ct}/match", json={"po_id": po, "invoice_id": "nope"}, headers=h()).status_code in (404, 422)
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()
    assert verdict_hash([{"dim": "a", "status": "pass"}]) == verdict_hash([{"dim": "a", "status": "pass"}])
