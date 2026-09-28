"""B-20 — what happens when the money control has no ceiling to check against.

`check_budget` used to return `{"checked": False}` when no budget row existed for
(category, period) and the approval proceeded. That is the historical reading of
"no ceiling set", but it is a silent pass on the one control whose job is to make
an overspend impossible, and an operator could reasonably expect the opposite: a
deployment that configures no budgets at all has a budget gate that never gates,
and nothing anywhere says so.

The choice is now `BUDGET_UNSET_POLICY`: `allow` (the default, today's behaviour)
or `block`, which turns the missing row into a 422 naming the category and the
period. Asserted in both directions — a test that only checked the block path
would have passed even if the gate refused every approval, which is the same
lesson B-02 records for the role check.

**Residual, stated:** a purchase order with no category assigned bypasses the
gate in both modes. There is no (category, period) to look up, so the policy
governs the missing row, not the missing category — `test_global_parity.py`
asserts the uncategorised path is unchanged.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from pydantic import ValidationError

from app.core.config import Settings
from .helpers import make_category

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def client(monkeypatch, request):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    policy = getattr(request, "param", None)
    if policy is not None:
        monkeypatch.setenv("BUDGET_UNSET_POLICY", policy)
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
    jwk["kid"] = "bp-kid"
    from app.core import security

    security.override_jwks({"bp-kid": RSAAlgorithm.from_jwk(jwk)})
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
                     pem, algorithm="RS256", headers={"kid": "bp-kid"})
    return {"Authorization": f"Bearer {tok}"}


def _open_po_with_category(client_fixture, *, code: str) -> str:
    """A PO awaiting approval, charged to a category that has no budget row."""
    c, pem = client_fixture
    h = _h(pem)
    s = c.post("/api/v1/suppliers", json={"code": f"SUP-{code}", "name": "Unset Budget Co"},
               headers=h).json()["data"]["id"]
    cat = make_category(c, h, f"CAT-{code}", "No ceiling here")
    po = c.post("/api/v1/purchase-orders", json={
        "code": code, "supplier_id": s, "category_id": cat,
        "lines": [{"description": "Widget", "quantity": 1, "unit_price_minor": 500_000}],
    }, headers=h).json()["data"]["id"]
    return po


# --- the policy -------------------------------------------------------------

@pytest.mark.parametrize("client", ["allow"], indirect=True)
def test_the_default_allows_an_approval_against_no_budget_row(client):
    """`allow` is the default, and it is today's behaviour: no ceiling set means
    the approval proceeds. Pinned so the default cannot drift into `block` —
    which would turn every deployment that configured no budgets into one where
    no purchase order can be approved at all."""
    c, pem = client
    assert Settings().budget_unset_policy == "allow"
    po = _open_po_with_category(client, code="PO-ALLOW")
    mgr = _h(pem, sub="mgr1", roles=("Procurement Manager",))
    res = c.post(f"/api/v1/purchase-orders/{po}/approve", headers=mgr)
    assert res.status_code == 200, res.text


@pytest.mark.parametrize("client", ["block"], indirect=True)
def test_block_refuses_an_approval_against_no_budget_row(client):
    """`block` is the reading an operator who expects 'no uncontrolled spend'
    has: a missing ceiling is a 422 that names the category and the period, not
    a silent pass on a money control."""
    c, pem = client
    po = _open_po_with_category(client, code="PO-BLOCK")
    mgr = _h(pem, sub="mgr1", roles=("Procurement Manager",))
    res = c.post(f"/api/v1/purchase-orders/{po}/approve", headers=mgr)
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "BUDGET_UNSET"
    assert res.json()["error"]["message"], "the refusal must say why"


@pytest.mark.parametrize("client", ["block"], indirect=True)
def test_block_still_enforces_a_real_ceiling(client):
    """`block` must not have traded the ceiling for the unset case: with a row
    present, the ordinary `BUDGET_EXCEEDED` gate still applies."""
    from app.routers.catalog import current_period

    c, pem = client
    h = _h(pem)
    s = c.post("/api/v1/suppliers", json={"code": "SUP-CEIL", "name": "Ceiling Co"},
               headers=h).json()["data"]["id"]
    cat = make_category(c, h, "CAT-CEIL", "Ceiling")
    assert c.post("/api/v1/budgets", json={"category_id": cat, "period": current_period(),
                  "ceiling_minor": 100_000}, headers=h).status_code == 201
    po = c.post("/api/v1/purchase-orders", json={
        "code": "PO-CEIL", "supplier_id": s, "category_id": cat,
        "lines": [{"description": "Steel", "quantity": 10, "unit_price_minor": 20_000}],
    }, headers=h).json()["data"]["id"]
    mgr = _h(pem, sub="mgr1", roles=("Procurement Manager",))
    over = c.post(f"/api/v1/purchase-orders/{po}/approve", headers=mgr)
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "BUDGET_EXCEEDED", (
        "the unset policy replaced the ceiling check rather than adding to it")


@pytest.mark.parametrize("client", ["block"], indirect=True)
def test_block_does_not_gate_an_uncategorised_po(client):
    """There is no (category, period) to look up when the PO has no category, so
    the strict mode governs the missing row and not the missing category. This
    is the residual, stated in the docstring — asserted here so it is a property
    and not a prose claim."""
    c, pem = client
    h = _h(pem)
    s = c.post("/api/v1/suppliers", json={"code": "SUP-NOCAT", "name": "No Cat Co"},
               headers=h).json()["data"]["id"]
    po = c.post("/api/v1/purchase-orders", json={
        "code": "PO-NOCAT", "supplier_id": s,
        "lines": [{"description": "Misc", "quantity": 1, "unit_price_minor": 999_999}],
    }, headers=h).json()["data"]["id"]
    mgr = _h(pem, sub="mgr1", roles=("Procurement Manager",))
    assert c.post(f"/api/v1/purchase-orders/{po}/approve", headers=mgr).status_code == 200


# --- the configuration ------------------------------------------------------

@pytest.mark.parametrize("raw", ["BLOCK", "fail-closed", "Block", "0", ""])
def test_a_misconfigured_policy_is_refused_at_startup(raw, monkeypatch):
    """A control whose misconfiguration is indistinguishable from its opposite is
    not a control. `BUDGET_UNSET_POLICY=BLOCK` used to be a value nobody had
    thought about: the call-site comparison was against the lowercase literals,
    so the typo silently behaved as `allow` while the configuration file claimed
    the opposite. Refused here, at startup read, rather than picked a default."""
    monkeypatch.delenv("BUDGET_UNSET_POLICY", raising=False)
    monkeypatch.setenv("BUDGET_UNSET_POLICY", raw)
    with pytest.raises(ValidationError):
        Settings()
