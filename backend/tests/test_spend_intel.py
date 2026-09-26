"""Spend intel tests — cube, leakage, maverick, concentration on real flows."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    engine = get_engine()
    from app.models.registry import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "si-kid"
    from app.core import security

    security.override_jwks({"si-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="buyer1", tenant="t1"):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": ["Buyer", "Procurement Manager"]},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "si-kid"})
    return {"Authorization": f"Bearer {tok}"}


def _po_flow(c, pem, tenant, sub, code, supplier, price, category=""):
    h = _h(pem, sub, tenant)
    po = c.post("/api/v1/purchase-orders", json={"code": code, "supplier_id": supplier, "category_id": category,
                "lines": [{"description": "Widget", "quantity": 10, "unit_price_minor": price}]}, headers=h).json()["data"]["id"]
    now = datetime.now(timezone.utc)
    mtok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "mgr-" + sub, "tenant_id": tenant,
                       "realm_access": {"roles": ["Procurement Manager"]},
                       "exp": now + timedelta(minutes=5), "iat": now}, pem, algorithm="RS256", headers={"kid": "si-kid"})
    mh = {"Authorization": f"Bearer {mtok}"}
    assert c.post(f"/api/v1/purchase-orders/{po}/approve", headers=mh).status_code == 200
    assert c.post(f"/api/v1/purchase-orders/{po}/send", headers=h).status_code == 200
    pod = c.get(f"/api/v1/purchase-orders/{po}", headers=h).json()["data"]
    plid = pod["lines"][0]["id"]
    assert c.post(f"/api/v1/purchase-orders/{po}/receipts", json={"lines": [{"po_line_id": plid, "quantity": 10}]}, headers=h).status_code == 201
    inv = c.post(f"/api/v1/purchase-orders/{po}/invoices", json={"code": f"INV-{code}",
                "lines": [{"po_line_id": plid, "quantity": 10, "unit_price_minor": price}]}, headers=h).json()["data"]["id"]
    assert c.post(f"/api/v1/invoices/{inv}/approve", headers=mh).status_code == 200
    return po


def test_intelligence_end_to_end(client):
    c, pem = client
    h = _h(pem, "u0", "acme")
    s1 = c.post("/api/v1/suppliers", json={"code": "S-1", "name": "Alpha"}, headers=h).json()["data"]["id"]
    s2 = c.post("/api/v1/suppliers", json={"code": "S-2", "name": "Beta"}, headers=h).json()["data"]["id"]
    # s1 has an active contract (covered); s2 does not (leakage)
    ct = c.post("/api/v1/contracts", json={"code": "CT-1", "title": "Cover Alpha", "supplier_id": s1, "value_minor": 10_000_000}, headers=h).json()["data"]["id"]
    c.patch(f"/api/v1/contracts/{ct}/status", json={"status": "review"}, headers=h)
    c.patch(f"/api/v1/contracts/{ct}/status", json={"status": "active"}, headers=h)
    _po_flow(c, pem, "acme", "u0", "P1", s1, 1000, category="CAT-A")
    _po_flow(c, pem, "acme", "u0", "P2", s2, 9000)  # uncategorized => maverick
    intel = c.get("/api/v1/spend/intelligence", headers=h).json()["data"]
    assert intel["cube"] != []
    assert intel["leakageTotalMinor"] == 90_000  # s2 invoice uncovered
    assert intel["maverickTotalMinor"] == 90_000  # P2 uncategorized
    assert intel["concentration"]["singleSourceRisk"] is True  # 90k/100k = 90%
    assert intel["concentration"]["topSupplier"] == s2
    # empty tenant => explicit zeros
    empty = c.get("/api/v1/spend/intelligence", headers=_h(pem, "u0", "void")).json()["data"]
    assert empty["cube"] == [] and empty["leakageTotalMinor"] == 0
    assert empty["concentration"] == {"topShareBp": 0, "topSupplier": "", "singleSourceRisk": False}
