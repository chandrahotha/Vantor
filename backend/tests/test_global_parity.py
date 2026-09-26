"""Global-parity tests — catalogs, budgets (hard gate), sign-off records."""
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
    jwk["kid"] = "gp-kid"
    from app.core import security

    security.override_jwks({"gp-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="buyer1", tenant="t1", roles=("Buyer", "Finance Reviewer")):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "gp-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_catalog_crud_and_prefill(client):
    c, pem = client
    h = _h(pem)
    r = c.post("/api/v1/catalog/items", json={"code": "BOLT-M10", "name": "Bolt M10", "uom": "each", "ref_price_minor": 500, "currency": "INR"}, headers=h)
    assert r.status_code == 201, r.text
    assert c.post("/api/v1/catalog/items", json={"code": "BOLT-M10", "name": "Dup"}, headers=h).status_code == 409
    lst = c.get("/api/v1/catalog/items?search=bolt", headers=h).json()["data"]
    assert len(lst) == 1 and lst[0]["refPriceMinor"] == 500


def test_budget_hard_gate_on_approve(client):
    from app.routers.catalog import current_period

    c, pem = client
    h = _h(pem)
    s = c.post("/api/v1/suppliers", json={"code": "SUP-B", "name": "Budget Parts"}, headers=h).json()["data"]["id"]
    assert c.post("/api/v1/budgets", json={"category_id": "CAT-STEEL", "period": current_period(), "ceiling_minor": 100_000}, headers=h).status_code == 201
    # PO within budget approves fine
    po1 = c.post("/api/v1/purchase-orders", json={"code": "PO-B1", "supplier_id": s, "category_id": "CAT-STEEL",
                 "lines": [{"description": "Steel", "quantity": 10, "unit_price_minor": 5000}]}, headers=h).json()["data"]["id"]
    mgr = _h(pem, sub="mgr1", roles=("Procurement Manager",))
    assert c.post(f"/api/v1/purchase-orders/{po1}/approve", headers=mgr).status_code == 200
    assert c.post(f"/api/v1/purchase-orders/{po1}/send", headers=h).status_code == 200
    # second PO breaches 100000 ceiling (50000 committed + 60000) => 422
    po2 = c.post("/api/v1/purchase-orders", json={"code": "PO-B2", "supplier_id": s, "category_id": "CAT-STEEL",
                 "lines": [{"description": "Steel", "quantity": 10, "unit_price_minor": 6000}]}, headers=h).json()["data"]["id"]
    over = c.post(f"/api/v1/purchase-orders/{po2}/approve", headers=mgr)
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "BUDGET_EXCEEDED"
    # uncategorized POs skip the gate (cannot scope)
    po3 = c.post("/api/v1/purchase-orders", json={"code": "PO-B3", "supplier_id": s,
                 "lines": [{"description": "Misc", "quantity": 1, "unit_price_minor": 999_999}]}, headers=h).json()["data"]["id"]
    assert c.post(f"/api/v1/purchase-orders/{po3}/approve", headers=mgr).status_code == 200


def test_contract_signoff(client):    c, pem = client
    h = _h(pem, roles=("Legal Reviewer",))
    ct = c.post("/api/v1/contracts", json={"code": "CT-S", "title": "Sign me"}, headers=h).json()["data"]["id"]
    # draft cannot be signed
    assert c.post(f"/api/v1/contracts/{ct}/sign", json={"method": "internal"}, headers=h).status_code == 422
    c.patch(f"/api/v1/contracts/{ct}/status", json={"status": "review"}, headers=h)
    s1 = c.post(f"/api/v1/contracts/{ct}/sign", json={"method": "internal"}, headers=h)
    assert s1.status_code == 201 and len(s1.json()["data"]["snapshotHash"]) == 64
    # esign without envelope refused
    assert c.post(f"/api/v1/contracts/{ct}/sign", json={"method": "esign", "provider": "docusign"}, headers=h).status_code == 422
    s2 = c.post(f"/api/v1/contracts/{ct}/sign", json={"method": "esign", "provider": "docusign", "envelope_id": "env-1"}, headers=h)
    assert s2.status_code == 201
    got = c.get(f"/api/v1/contracts/{ct}", headers=h).json()["data"]
    assert got["obligationCount"] == 0
